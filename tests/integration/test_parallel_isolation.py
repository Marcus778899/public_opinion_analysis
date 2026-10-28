"""平行執行的防呆（開發規格 7.26）：Kafka cluster_id 比對、全域重置只做一次、worker 隔離。"""

import re
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from confluent_kafka.admin import AdminClient, NewTopic
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from radar.common.clickhouse import load_migrations
from radar.common.kafka.config import admin_config
from radar.common.settings import ClickHouseSettings, KafkaSettings
from tests.helpers import clickhouse as ch_helper
from tests.helpers.clickhouse import worker_database
from tests.integration import conftest as it_conftest
from tests.integration._xdist import run_once

REPO = Path(__file__).resolve().parents[2]


def test_reset_kafka_cluster_id_mismatch_refuses_without_deleting():
    admin = MagicMock()
    admin.list_topics.return_value.cluster_id = "dev-cluster"
    admin.list_topics.return_value.topics = {"orders": object()}
    settings = KafkaSettings(bootstrap_servers="localhost:9092", client_id="it")

    with (
        patch.object(it_conftest, "AdminClient", return_value=admin),
        pytest.raises(pytest.exit.Exception),
    ):
        it_conftest.reset_kafka(settings)

    admin.delete_topics.assert_not_called()
    admin.create_topics.assert_not_called()


def test_reset_kafka_wrong_expected_cluster_id_keeps_real_topics(kafka_settings):
    admin = AdminClient(admin_config(kafka_settings))
    keep = f"it.guard.{uuid.uuid4().hex[:8]}"
    admin.create_topics([NewTopic(keep, 1, 1)])[keep].result(30)

    with pytest.raises(pytest.exit.Exception):
        it_conftest.reset_kafka(kafka_settings, expected_cluster_id="not-this-cluster")

    assert keep in admin.list_topics(timeout=30).topics


def test_running_kafka_has_the_expected_test_cluster_id(kafka_settings):
    admin = AdminClient(admin_config(kafka_settings))

    assert admin.list_topics(timeout=30).cluster_id == it_conftest.KAFKA_TEST_CLUSTER_ID


def test_compose_cluster_id_matches_conftest_and_differs_from_dev_env():
    compose = yaml.safe_load((REPO / "compose.yaml").read_text())
    in_compose = compose["services"]["kafka"]["environment"]["CLUSTER_ID"]
    dev = re.search(r"^CLUSTER_ID=(\S+)", (REPO / ".env.example").read_text(), re.M)

    assert in_compose == it_conftest.KAFKA_TEST_CLUSTER_ID
    assert dev is not None
    assert in_compose != dev.group(1)


def test_run_once_without_xdist_runs_every_time(monkeypatch, tmp_path):
    monkeypatch.delenv("PYTEST_XDIST_TESTRUNUID", raising=False)
    calls: list[int] = []

    run_once("k", lambda: calls.append(1), tmp_path)
    run_once("k", lambda: calls.append(1), tmp_path)

    assert len(calls) == 2


def test_run_once_with_same_run_id_runs_once(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTEST_XDIST_TESTRUNUID", uuid.uuid4().hex)
    calls: list[int] = []

    run_once("k", lambda: calls.append(1), tmp_path)
    run_once("k", lambda: calls.append(1), tmp_path)

    assert len(calls) == 1


def test_run_once_after_failure_makes_other_workers_stop(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTEST_XDIST_TESTRUNUID", uuid.uuid4().hex)

    def boom() -> None:
        raise RuntimeError("reset failed")

    with pytest.raises(RuntimeError):
        run_once("k", boom, tmp_path)
    with pytest.raises(pytest.exit.Exception):
        run_once("k", lambda: None, tmp_path)


def test_worker_database_name_is_prefixed_and_rejects_unsafe_ids():
    assert worker_database("gw3") == "radar_gw3"
    with pytest.raises(ValueError):
        worker_database("gw0; DROP")


def test_postgres_url_points_at_this_workers_own_database(postgres_url, worker):
    engine = create_engine(postgres_url)
    try:
        with engine.connect() as conn:
            db = conn.execute(text("SELECT current_database()")).scalar_one()
    finally:
        engine.dispose()

    assert db == f"radar_it_{worker}"


def test_pg_admin_refuses_a_database_other_than_radar_it(postgres_url):
    with pytest.raises(pytest.exit.Exception):
        it_conftest.reset_postgres(postgres_url)


def test_clickhouse_radar_database_is_current_after_session_reset(clickhouse_settings):
    assert ch_helper.is_current(clickhouse_settings)


@pytest.mark.parametrize("url", ["http://prod-clickhouse:8123", "http://ch.dev.example.com:8123"])
def test_reset_keeping_radar_non_test_target_refuses_without_dropping(url):
    client = MagicMock()
    settings = ClickHouseSettings(url=url, db="radar", user="radar", password=SecretStr("it"))

    with (
        patch.object(ch_helper, "ClickHouseClient", return_value=client),
        pytest.raises(PermissionError),
    ):
        ch_helper.reset_keeping_radar(settings)

    client.execute.assert_not_called()


def test_without_kafka_removes_engine_tables_and_views_only():
    migrations = load_migrations(ch_helper.CH_DIR / "migrations")

    kept = [s for m in ch_helper.without_kafka(migrations) for s in m.statements]

    assert kept
    assert not any("ENGINE = Kafka" in s for s in kept)
    assert not any(ch_helper.is_kafka_statement(s) for s in kept)
    assert any("CREATE TABLE IF NOT EXISTS labels" in s for s in kept)


def test_reset_kafka_keep_leaves_kept_topics_and_deletes_the_rest():
    admin = MagicMock()
    states = iter([["keep_me", "drop_me"], ["keep_me"]])
    admin.list_topics.side_effect = lambda timeout: MagicMock(
        topics={t: object() for t in next(states, ["keep_me"])}
    )
    admin.delete_topics.return_value = {"drop_me": MagicMock()}
    settings = KafkaSettings(bootstrap_servers="kafka_1:29092", client_id="it")

    with patch.object(it_conftest, "check_kafka_target", return_value=admin):
        it_conftest.reset_kafka(settings, keep=("keep_me",))

    admin.delete_topics.assert_called_once_with(["drop_me"])
    created = [t.topic for t in admin.create_topics.call_args.args[0]]
    assert "keep_me" not in created
    assert set(created) == set(it_conftest.CLICKHOUSE_TOPICS)
