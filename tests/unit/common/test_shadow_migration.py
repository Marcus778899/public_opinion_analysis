"""0006 的 predictions_shadow 與 predictions 結構一致、訂閱 predictions.shadow（開發規格 7.27）。"""

import re
from pathlib import Path

from radar.common.clickhouse import load_migrations
from radar.common.kafka import names
from radar.common.settings import InferenceRole
from radar.ml.inference.roles import ROLE_TARGETS

MIGRATIONS = Path(__file__).resolve().parents[3] / "infra/clickhouse/migrations"
_CREATE = re.compile(r"CREATE (?:TABLE|MATERIALIZED VIEW) IF NOT EXISTS (\w+)")


def statements() -> dict[str, str]:
    """套完全部 migration 後，各表最後一次的 CREATE 語句。"""
    found: dict[str, str] = {}
    for migration in load_migrations(MIGRATIONS):
        for s in migration.statements:
            if m := _CREATE.search(s):
                found[m.group(1)] = s
    return found


def columns(statement: str) -> list[str]:
    body = statement.split("(", 1)[1].split("ENGINE")[0]
    return [line.split()[0] for line in body.splitlines() if line.strip() not in ("", ")")]


def test_shadow_queue_columns_match_predictions_queue():
    created = statements()

    assert columns(created["predictions_shadow_queue"]) == columns(created["predictions_queue"])


def test_shadow_table_has_predictions_columns_including_text_hash():
    created = statements()

    shadow = columns(created["predictions_shadow"])

    assert shadow == [*columns(created["predictions"]), "text_hash"]


def test_shadow_queue_subscribes_shadow_topic_with_own_group():
    queue = statements()["predictions_shadow_queue"]

    assert f"kafka_topic_list = '{names.PREDICTIONS_SHADOW}'" in queue
    assert "kafka_group_name = 'clickhouse-predictions-shadow'" in queue


def test_shadow_mv_writes_role_table():
    mv = statements()["predictions_shadow_mv"]

    assert f"TO {ROLE_TARGETS[InferenceRole.SHADOW].table} AS" in mv
    assert "FROM predictions_shadow_queue" in mv
