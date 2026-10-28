from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from radar.common.clickhouse import ClickHouseError, Migration, load_migrations
from radar.common.settings import ClickHouseSettings
from tests.helpers import clickhouse as ch_helper

KAFKA_TABLE = (
    "CREATE TABLE IF NOT EXISTS a_queue (x Int32) ENGINE = Kafka(c, kafka_topic_list = 'a')"
)
QUEUE_MV = "CREATE MATERIALIZED VIEW IF NOT EXISTS a_mv TO a AS\nSELECT x\nFROM a_queue"
PLAIN_MV = "CREATE MATERIALIZED VIEW IF NOT EXISTS b_mv TO b AS\nSELECT x\nFROM a_latest FINAL"
PLAIN_TABLE = "CREATE TABLE IF NOT EXISTS a (x Int32) ENGINE = MergeTree ORDER BY x"


def _settings() -> ClickHouseSettings:
    return ClickHouseSettings(
        url="http://clickhouse:8123", db="radar", user="radar", password=SecretStr("it")
    )


def test_without_kafka_mv_reading_queue_is_removed_and_plain_mv_kept():
    migrations = [Migration(1, "m", [KAFKA_TABLE, PLAIN_TABLE, QUEUE_MV, PLAIN_MV])]

    kept = ch_helper.without_kafka(migrations)[0].statements

    assert kept == [PLAIN_TABLE, PLAIN_MV]


def test_without_kafka_real_migrations_keeps_no_queue_reader():
    kept = [
        s
        for m in ch_helper.without_kafka(load_migrations(ch_helper.CH_DIR / "migrations"))
        for s in m.statements
    ]

    assert kept
    creates = [s for s in kept if s.lstrip().upper().startswith("CREATE")]
    assert not any("ENGINE = Kafka" in s or "FROM " in s and "_queue" in s for s in creates)


def test_kafka_objects_dropped_object_is_excluded_and_recreated_one_included():
    migrations = [
        Migration(1, "a", [KAFKA_TABLE, QUEUE_MV, PLAIN_MV]),
        Migration(2, "b", ["DROP VIEW IF EXISTS a_mv", KAFKA_TABLE.replace("a_queue", "c_queue")]),
        Migration(3, "c", [QUEUE_MV]),
    ]

    assert ch_helper.kafka_objects(migrations) == {"a_queue", "c_queue", "a_mv"}


def _current(applied: set[int] | None, tables: list[str] | Exception) -> bool:
    migrations = load_migrations(ch_helper.CH_DIR / "migrations")
    return _run(applied if applied is not None else {m.version for m in migrations}, tables)


def _run(applied: set[int], tables: list[str] | Exception) -> bool:
    client = MagicMock()
    if isinstance(tables, Exception):
        client.execute.side_effect = tables
    else:
        client.execute.return_value = "\n".join(tables)
    with (
        patch.object(ch_helper, "ClickHouseClient", return_value=client),
        patch.object(ch_helper, "applied_versions", return_value=applied),
    ):
        return ch_helper.is_current(_settings())


def _expected() -> list[str]:
    migrations = load_migrations(ch_helper.CH_DIR / "migrations")
    return sorted(ch_helper.kafka_objects(migrations))


def test_is_current_all_migrations_and_kafka_objects_present_returns_true():
    assert _current(None, _expected()) is True


def test_is_current_kafka_table_missing_returns_false():
    assert _current(None, _expected()[1:]) is False


def test_is_current_missing_migration_returns_false():
    assert _current({1}, _expected()) is False


def test_is_current_clickhouse_error_returns_false():
    assert _current(None, ClickHouseError("boom")) is False
