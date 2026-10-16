import pytest

from radar.common.clickhouse import ClickHouseError
from radar.ml.inference.backfill_hash import (
    HashUpdate,
    MissingHash,
    apply_updates,
    build_updates,
    fetch_missing,
    update_statement,
)
from radar.ml.inference.main import text_hash

PID = "Stock.M.1792000000.A.ABC"
PID2 = "Gossiping.M.1792000001.A.DEF"
AT = "2026-10-16 07:44:02.548809"
H = "a" * 64
MV = "tfidf-lr-202610151237"


class FakeClickHouse:
    def __init__(self, rows=(), fail_on: int | None = None) -> None:
        self.rows = list(rows)
        self.fail_on = fail_on
        self.queries: list[tuple[str, dict[str, str] | None]] = []
        self.executed: list[str] = []

    def query_rows(self, sql, params=None):
        self.queries.append((sql, params))
        return self.rows

    def execute(self, sql, params=None):
        if self.fail_on is not None and len(self.executed) == self.fail_on:
            raise ClickHouseError("500: mutation failed")
        self.executed.append(sql)
        return ""


def update(post_id: str = PID, predicted_at: str = AT, digest: str = H) -> HashUpdate:
    return HashUpdate(post_id, predicted_at, digest)


# --- build_updates ---


def test_build_updates_hash_matches_inference_text_hash():
    [u] = build_updates([MissingHash(PID, AT)], {PID: "標題\n內文"})

    assert u == HashUpdate(PID, AT, text_hash("標題\n內文"))


def test_build_updates_post_missing_in_pg_is_skipped():
    updates = build_updates([MissingHash(PID, AT), MissingHash(PID2, AT)], {PID2: "x"})

    assert [u.post_id for u in updates] == [PID2]


def test_build_updates_empty_missing_returns_empty():
    assert build_updates([], {PID: "x"}) == []


# --- update_statement ---


def test_update_statement_only_touches_rows_with_empty_hash_of_model_version():
    sql = update_statement(MV, [update()])

    assert sql.startswith("ALTER TABLE predictions UPDATE text_hash = ")
    assert f"model_version = '{MV}' AND text_hash = ''" in sql
    assert "mutations_sync = 2" in sql


def test_update_statement_keys_by_post_id_and_predicted_at():
    sql = update_statement(MV, [update(), update(PID2, AT, "b" * 64)])

    assert f"['{PID}|{AT}', '{PID2}|{AT}']" in sql
    assert f"['{H}', '{'b' * 64}']" in sql
    assert "concat(post_id, '|', toString(predicted_at))" in sql


def test_update_statement_post_id_with_quote_rejected():
    with pytest.raises(ValueError):
        update_statement(MV, [update(post_id="Stock.M.1.A.ABC'; DROP TABLE predictions; --")])


@pytest.mark.parametrize("bad", ["2026-10-16 07:44:02", "2026-10-16' OR 1=1 --"])
def test_update_statement_invalid_predicted_at_rejected(bad):
    with pytest.raises(ValueError, match="predicted_at"):
        update_statement(MV, [update(predicted_at=bad)])


@pytest.mark.parametrize("bad", ["", "A" * 64, "a" * 63, "'" + "a" * 63])
def test_update_statement_invalid_hash_rejected(bad):
    with pytest.raises(ValueError, match="text_hash"):
        update_statement(MV, [update(digest=bad)])


def test_update_statement_invalid_model_version_rejected():
    with pytest.raises(ValueError, match="model_version"):
        update_statement("v1' OR 1=1 --", [update()])


def test_update_statement_empty_updates_rejected():
    with pytest.raises(ValueError, match="no updates"):
        update_statement(MV, [])


# --- fetch_missing / apply_updates ---


def test_fetch_missing_passes_model_version_param():
    ch = FakeClickHouse([{"post_id": PID, "latest_at": AT}])

    missing = fetch_missing(ch, MV)

    assert missing == [MissingHash(PID, AT)]
    [(sql, params)] = ch.queries
    assert params == {"model_version": MV}
    assert "argMax(text_hash, predicted_at) = ''" in sql


def test_apply_updates_splits_into_batches_and_returns_count():
    ch = FakeClickHouse()
    updates = [update(f"Stock.M.{1792000000 + i}.A.ABC") for i in range(5)]

    assert apply_updates(ch, MV, updates, batch_size=2) == 5
    assert len(ch.executed) == 3
    assert "Stock.M.1792000004.A.ABC" in ch.executed[2]


def test_apply_updates_no_updates_executes_nothing():
    ch = FakeClickHouse()

    assert apply_updates(ch, MV, [], batch_size=2) == 0
    assert ch.executed == []


def test_apply_updates_clickhouse_error_propagates():
    ch = FakeClickHouse(fail_on=1)
    updates = [update(f"Stock.M.{1792000000 + i}.A.ABC") for i in range(4)]

    with pytest.raises(ClickHouseError):
        apply_updates(ch, MV, updates, batch_size=2)
    assert len(ch.executed) == 1
