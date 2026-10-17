import json
import logging
from datetime import UTC, datetime, timedelta

import pytest

from radar.common.kafka.consumer import DecodeError
from radar.common.schemas import Alert, CdcComment
from radar.common.settings import HeatSettings
from radar.streaming.heat import (
    STATE_KEY,
    BoardHeat,
    CdcCommentDeserializer,
    Ewma,
    HeatConfig,
    Trigger,
    advance,
    alert_id,
    close_minute,
    counts_event,
    event_minute,
    is_decode_error,
    is_fresh,
    make_on_consumer_error,
    min_count_for,
    minute_end,
    post_baseline_values,
    process,
    record,
    to_alert,
    top_posts,
    window_count,
)

BOARD = "Stock"
PID = "Stock.M.1792000000.A.ABC"
PID2 = "Stock.M.1792000001.A.DEF"
T0 = 29_000_000  # epoch 分鐘
# NOTE: 文章門檻設成與看板相同，既有案例才能用小量推文測觸發邏輯；#59 的門檻另外測
CFG = HeatConfig(warmup_min=5, max_gap_min=100, post_min_count=30)


def at(minute: int) -> datetime:
    return datetime.fromtimestamp(minute * 60 + 30, UTC)


def comment(minute: int | None, post_id: str = PID, op: str = "c", **kw) -> CdcComment:
    return CdcComment.model_validate(
        {
            "post_id": post_id,
            "floor": 1,
            "type": "push",
            "commented_at": at(minute) if minute is not None else None,
            "__op": op,
            **kw,
        }
    )


def warmed(minutes: int = 10, per_minute: int = 1, start: int = T0) -> BoardHeat:
    """每分鐘 per_minute 則推文、持續 minutes 分鐘，基準已暖機的看板。"""
    state = BoardHeat(BOARD)
    for m in range(start, start + minutes):
        for _ in range(per_minute):
            record(state, comment(m), now_min=m, config=CFG)
    return state


# --- Ewma ---


def test_ewma_first_sample_becomes_mean():
    e = Ewma()

    e.update(7, 0.1)

    assert (e.mean, e.var, e.samples) == (7, 0, 1)


def test_ewma_update_moves_mean_toward_value_by_alpha():
    e = Ewma(mean=10, var=0, samples=1)

    e.update(20, 0.1)

    assert e.mean == pytest.approx(11)
    assert e.var == pytest.approx(0.9 * (0 + 10 * 1))


def test_ewma_constant_input_variance_stays_zero():
    e = Ewma()
    for _ in range(50):
        e.update(5, 0.2)

    assert (e.mean, e.var) == (pytest.approx(5), pytest.approx(0))


def test_ewma_update_pooled_single_value_matches_update():
    pooled, single = Ewma(mean=10, var=4, samples=3), Ewma(mean=10, var=4, samples=3)

    pooled.update_pooled([20], 0.1)
    single.update(20, 0.1)

    assert (pooled.mean, pooled.var) == (pytest.approx(single.mean), pytest.approx(single.var))
    assert pooled.samples == 4


def test_ewma_update_pooled_first_call_uses_batch_mean_and_spread():
    e = Ewma()

    e.update_pooled([2, 4, 6], 0.1)

    assert (e.mean, e.var, e.samples) == (pytest.approx(4), pytest.approx(8 / 3), 1)


def test_ewma_update_pooled_spread_between_values_raises_variance():
    same, spread = Ewma(mean=5, var=0, samples=10), Ewma(mean=5, var=0, samples=10)

    same.update_pooled([5, 5], 0.1)
    spread.update_pooled([1, 9], 0.1)

    assert same.mean == spread.mean == pytest.approx(5)
    assert (same.var, spread.var) == (pytest.approx(0), pytest.approx(0.1 * 16))


def test_ewma_update_pooled_empty_values_is_noop():
    e = Ewma(mean=5, var=1, samples=10)

    e.update_pooled([], 0.1)

    assert e == Ewma(mean=5, var=1, samples=10)


def test_ewma_zscore_uses_min_std_when_variance_tiny():
    e = Ewma(mean=2, var=0.01, samples=10)

    assert e.zscore(12, min_std=1.0) == pytest.approx(10)
    assert Ewma(mean=2, var=16, samples=10).zscore(12, min_std=1.0) == pytest.approx(2.5)


# --- event_minute / counts_event ---


def test_event_minute_uses_observation_time():
    observed = (T0 + 8) * 60_000 + 59_000

    assert event_minute(comment(T0, __source_ts_ms=observed)) == T0 + 8


def test_event_minute_falls_back_to_commented_at():
    assert event_minute(comment(T0)) == T0


def test_event_minute_without_any_time_raises():
    with pytest.raises(ValueError, match="no time"):
        event_minute(comment(None))


def test_is_fresh_within_max_delay():
    assert is_fresh(comment(T0, __source_ts_ms=(T0 + 30) * 60_000 + 30_000), 30) is True


def test_is_fresh_beyond_max_delay():
    assert is_fresh(comment(T0, __source_ts_ms=(T0 + 31) * 60_000 + 31_000), 30) is False


def test_is_fresh_missing_either_time_counts():
    assert is_fresh(comment(None, __source_ts_ms=1), 30) is True
    assert is_fresh(comment(T0), 30) is True


@pytest.mark.parametrize(
    ("op", "expected"), [("c", True), ("u", False), ("d", False), ("r", False)]
)
def test_counts_event_only_create(op, expected):
    assert counts_event(comment(T0, op=op)) is expected


def test_counts_event_pg_deleted_row_not_counted():
    assert counts_event(comment(T0, __deleted="true")) is False


# --- window_count / advance ---


def test_window_count_sums_last_window_minutes_inclusive_end():
    counts = {T0 - 10: 100, T0 - 9: 1, T0: 2, T0 + 1: 50}

    assert window_count(counts, T0, 10) == 3


def test_advance_updates_board_baseline_once_per_closed_minute():
    state = BoardHeat(BOARD, watermark=T0, board_counts={T0: 4})

    advance(state, T0 + 3, T0 + 3, CFG)

    assert state.board_baseline.samples == 3
    assert state.watermark == T0 + 3


def test_advance_first_minute_only_sets_watermark():
    state = BoardHeat(BOARD)

    assert advance(state, T0, T0, CFG) == []
    assert (state.watermark, state.board_baseline.samples) == (T0, 0)


def test_advance_fills_gap_minutes_with_zero():
    state = BoardHeat(BOARD, watermark=T0, board_counts={T0 - 20: 4})

    advance(state, T0 + 5, T0 + 5, CFG)

    assert state.board_baseline.mean == 0  # 視窗內都沒有推文，補的都是 0


def test_advance_caps_gap_at_max_gap_min():
    state = BoardHeat(BOARD, watermark=T0)

    advance(state, T0 + 10_000, T0 + 10_000, HeatConfig(max_gap_min=30))

    assert state.board_baseline.samples == 30


def test_advance_post_baseline_only_from_active_posts():
    state = BoardHeat(BOARD, watermark=T0, post_counts={PID: {T0: 6}, PID2: {T0 - 30: 9}})

    advance(state, T0 + 1, T0 + 1, CFG)

    assert (state.post_baseline.samples, state.post_baseline.mean) == (1, 6)


def test_advance_post_baseline_once_per_minute_regardless_of_active_posts():
    many = {f"Stock.M.{i}.A.000": {T0: 5} for i in range(40)}
    state = BoardHeat(BOARD, watermark=T0, post_counts=many)

    advance(state, T0 + 3, T0 + 3, CFG)

    assert state.post_baseline.samples == 3


def test_advance_post_baseline_decays_like_board_baseline():
    # 重現 #49：40 篇活躍文章時，舊的高基準 1 分鐘就幾乎被洗掉
    many = {f"Stock.M.{i}.A.000": {T0: 1} for i in range(40)}
    state = BoardHeat(
        BOARD,
        watermark=T0,
        board_counts={T0: 1},
        post_counts=many,
        board_baseline=Ewma(mean=100, var=0, samples=100),
        post_baseline=Ewma(mean=100, var=0, samples=100),
    )

    advance(state, T0 + 1, T0 + 1, CFG)

    assert state.post_baseline.mean == pytest.approx(state.board_baseline.mean)


def test_advance_post_baseline_skips_minute_without_active_posts():
    state = BoardHeat(BOARD, watermark=T0, post_baseline=Ewma(mean=8, var=2, samples=50))

    advance(state, T0 + 3, T0 + 3, CFG)

    assert state.post_baseline == Ewma(mean=8, var=2, samples=50)


def test_post_baseline_values_excludes_posts_in_cooldown():
    state = BoardHeat(
        BOARD,
        watermark=T0,
        post_counts={PID: {T0: 3}, PID2: {T0: 90}, "x": {T0 - 30: 9}},
        last_alert={f"post:{PID2}": T0 - 5},
    )

    assert post_baseline_values(state, T0, CFG) == [3]


def test_advance_drops_counts_older_than_window_plus_grace():
    state = BoardHeat(BOARD, watermark=T0, board_counts={T0 - 30: 1, T0 - 5: 1, T0: 1})

    advance(state, T0 + 10, T0 + 10, CFG)

    assert sorted(state.board_counts) == [T0]


def test_advance_removes_posts_without_recent_comments():
    state = BoardHeat(BOARD, watermark=T0, post_counts={PID: {T0: 1}, PID2: {T0 - 30: 1}})

    advance(state, T0 + 1, T0 + 1, CFG)

    assert list(state.post_counts) == [PID]


def test_advance_backwards_minute_is_noop():
    state = BoardHeat(BOARD, watermark=T0)

    assert advance(state, T0 - 3, T0, CFG) == []
    assert (state.watermark, state.board_baseline.samples) == (T0, 0)


def test_advance_drops_expired_cooldown_entries():
    state = BoardHeat(BOARD, watermark=T0, last_alert={f"post:{PID}": T0 - 40, "board:Stock": T0})

    advance(state, T0 + 1, T0 + 1, CFG)

    assert state.last_alert == {"board:Stock": T0}


# --- close_minute ---


def hot(post_counts: dict[str, dict[int, int]], **kw) -> BoardHeat:
    """基準已暖機（平均 1、變異 1）的看板，用來直接測 close_minute。"""
    base = {"mean": 1.0, "var": 1.0, "samples": 100}
    return BoardHeat(
        BOARD,
        watermark=T0 + 1,
        board_counts={T0: sum(c.get(T0, 0) for c in post_counts.values())},
        post_counts=post_counts,
        board_baseline=Ewma(**base),
        post_baseline=Ewma(**base),
        **kw,
    )


def test_close_minute_zscore_uses_baseline_before_update():
    state = hot({PID: {T0: 50}})

    [post] = [t for t in close_minute(state, T0, T0 + 1, CFG) if t.unit_type == "post"]

    assert (post.baseline, post.zscore) == (pytest.approx(1), pytest.approx(49))


def test_close_minute_evaluates_every_active_post():
    state = hot({PID: {T0: 50}, PID2: {T0: 60}})

    triggers = close_minute(state, T0, T0 + 1, CFG)

    assert sorted(t.unit_key for t in triggers if t.unit_type == "post") == [PID, PID2]


def test_close_minute_stale_minute_updates_baseline_without_trigger():
    state = hot({PID: {T0: 50}})

    assert close_minute(state, T0, T0 + 61, CFG) == []
    assert state.board_baseline.samples == 101


def test_close_minute_triggered_post_not_in_post_baseline():
    state = hot({PID: {T0: 50}, PID2: {T0: 1}})

    close_minute(state, T0, T0 + 1, CFG)

    assert state.post_baseline.mean == pytest.approx(1)  # 只納入 PID2 的 1


def test_close_minute_window_end_is_closed_minute():
    state = hot({PID: {T0: 50}})

    triggers = close_minute(state, T0, T0 + 1, CFG)

    assert {t.window_end_min for t in triggers} == {T0}


def test_min_count_for_post_uses_post_min_count():
    assert min_count_for("post", HeatConfig(min_count=30, post_min_count=80)) == 80


def test_min_count_for_board_uses_min_count():
    assert min_count_for("board", HeatConfig(min_count=30, post_min_count=80)) == 30


def test_close_minute_post_below_post_min_count_only_board_triggers():
    # 重現 #59：文章基準約 1，視窗值 50 的 z-score 很高，原本只要過 30 就觸發
    state = hot({PID: {T0: 50}})
    config = HeatConfig(warmup_min=5, post_min_count=80)

    triggers = close_minute(state, T0, T0 + 1, config)

    assert [t.unit_type for t in triggers] == ["board"]


def test_close_minute_post_at_post_min_count_triggers():
    state = hot({PID: {T0: 80}})
    config = HeatConfig(warmup_min=5, post_min_count=80)

    triggers = close_minute(state, T0, T0 + 1, config)

    assert [t.unit_key for t in triggers if t.unit_type == "post"] == [PID]


# --- record ---


def surge(state: BoardHeat, minute: int, n: int, post_id: str = PID) -> list[Trigger]:
    triggers: list[Trigger] = []
    for _ in range(n):
        triggers += record(state, comment(minute, post_id=post_id), now_min=minute, config=CFG)
    return triggers


def close(state: BoardHeat, minute: int) -> list[Trigger]:
    """送一則下一分鐘的零星推文，讓 minute 結算。"""
    return record(state, comment(minute + 1), now_min=minute + 1, config=CFG)


def test_record_late_comment_beyond_grace_is_dropped():
    state = BoardHeat(BOARD, watermark=T0)

    record(state, comment(T0 - 3), now_min=T0, config=CFG)

    assert state.board_counts == {}


def test_record_late_comment_within_grace_is_counted():
    state = BoardHeat(BOARD, watermark=T0)

    record(state, comment(T0 - 2), now_min=T0, config=CFG)

    assert state.board_counts == {T0 - 2: 1}
    assert state.watermark == T0


def test_record_late_comment_for_closed_minute_not_reevaluated():
    state = warmed()
    surge(state, T0 + 10, 25, post_id=PID2)
    close(state, T0 + 10)

    late = surge(state, T0 + 10, 25, post_id=PID2)  # 寬限內，但 T0 + 10 已結算

    assert late == []
    assert state.post_counts[PID2][T0 + 10] == 50


def test_record_delayed_comment_not_counted():
    state = BoardHeat(BOARD)
    late = comment(T0, __source_ts_ms=(T0 + 45) * 60_000)  # 補抓：推文時間早 45 分鐘

    assert record(state, late, now_min=T0 + 45, config=CFG) == []
    assert (state.board_counts, state.watermark) == ({}, None)


def test_record_counts_by_observation_minute():
    state = BoardHeat(BOARD)

    record(state, comment(T0, __source_ts_ms=(T0 + 8) * 60_000), now_min=T0 + 8, config=CFG)

    assert state.board_counts == {T0 + 8: 1}


def test_record_stale_comment_updates_baseline_without_trigger():
    state = warmed()
    m = T0 + 10

    triggers = [t for _ in range(60) for t in record(state, comment(m), m + 61, CFG)]
    triggers += record(state, comment(m + 1), m + 62, CFG)

    assert triggers == []
    assert state.board_counts[m] == 60


def test_record_surge_does_not_alert_before_minute_closes():
    state = warmed()

    assert surge(state, T0 + 10, 200, post_id=PID2) == []


def test_record_surge_alert_value_is_count_at_minute_close():
    # 重現 #50：原本在第 30 則就觸發，value 停在 30
    state = warmed()
    surge(state, T0 + 10, 200, post_id=PID2)

    triggers = close(state, T0 + 10)

    [post] = [t for t in triggers if t.unit_type == "post"]
    assert (post.unit_key, post.value, post.sample_post_ids) == (PID2, 200, [PID2])
    assert post.zscore >= CFG.z_threshold


def test_record_board_surge_triggers_board_alert():
    state = warmed()
    surge(state, T0 + 10, 40, post_id=PID2)

    triggers = close(state, T0 + 10)

    [board] = [t for t in triggers if t.unit_type == "board"]
    assert board.unit_key == BOARD
    assert board.sample_post_ids == [PID2, PID]


def test_record_below_min_count_does_not_trigger():
    state = warmed()
    surge(state, T0 + 10, 15, post_id=PID2)

    assert close(state, T0 + 10) == []


def test_record_below_z_threshold_does_not_trigger():
    state = warmed(per_minute=40)  # 平常每分鐘 40 則，視窗約 400
    surge(state, T0 + 10, 45)

    assert [t for t in close(state, T0 + 10) if t.unit_type == "board"] == []


def test_record_before_warmup_does_not_trigger():
    state = warmed(minutes=3)
    surge(state, T0 + 3, 60, post_id=PID2)

    assert close(state, T0 + 3) == []


def test_record_same_unit_within_cooldown_triggers_once():
    state = warmed()

    surge(state, T0 + 10, 40, post_id=PID2)
    first = close(state, T0 + 10)
    surge(state, T0 + 12, 40, post_id=PID2)
    again = close(state, T0 + 12)

    assert len([t for t in first if t.unit_type == "post"]) == 1
    assert [t for t in again if t.unit_type == "post"] == []


def test_record_after_cooldown_triggers_again():
    state = warmed()
    surge(state, T0 + 10, 40, post_id=PID2)
    for m in range(T0 + 11, T0 + 45):  # 冷卻期間只有零星推文
        record(state, comment(m), now_min=m, config=CFG)

    surge(state, T0 + 45, 40, post_id=PID2)
    triggers = close(state, T0 + 45)

    # 冷卻中的暴增不進文章基準，第二次同樣規模就會觸發
    assert [t.unit_key for t in triggers if t.unit_type == "post"] == [PID2]


# --- Trigger → Alert ---


def test_top_posts_orders_by_count_then_post_id():
    state = BoardHeat(
        BOARD,
        post_counts={"Stock.M.3.A.003": {T0: 2}, PID2: {T0: 5}, PID: {T0: 2}, "x": {T0 - 30: 9}},
    )

    assert top_posts(state, T0, 10) == [PID2, PID, "Stock.M.3.A.003"]


def test_alert_id_same_inputs_same_uuid():
    end = minute_end(T0)

    assert alert_id("post", PID, end) == alert_id("post", PID, end)


def test_alert_id_different_window_end_different_uuid():
    assert alert_id("post", PID, minute_end(T0)) != alert_id("post", PID, minute_end(T0 + 1))
    assert alert_id("post", PID, minute_end(T0)) != alert_id("board", PID, minute_end(T0))


def test_to_alert_window_start_is_window_minutes_before_end():
    trigger = Trigger("post", PID, T0, 40, 3.21, 9.87654, [PID])
    created = datetime(2026, 10, 17, tzinfo=UTC)

    alert = to_alert(trigger, BOARD, CFG, created)

    assert alert.window_end == datetime.fromtimestamp((T0 + 1) * 60, UTC)
    assert alert.window_end - alert.window_start == timedelta(minutes=10)
    assert (alert.value, alert.baseline, alert.zscore) == (40, 3.21, 9.877)
    assert alert.alert_id == alert_id("post", PID, alert.window_end)


def test_to_alert_board_keeps_sample_posts():
    trigger = Trigger("board", BOARD, T0, 80, 10, 5, [PID2, PID])

    alert = to_alert(trigger, BOARD, CFG, datetime(2026, 10, 17, tzinfo=UTC))

    assert (alert.unit_type, alert.unit_key, alert.sample_post_ids) == ("board", BOARD, [PID2, PID])


# --- state 序列化 ---


def test_board_heat_to_dict_from_dict_roundtrip():
    state = warmed()
    surge(state, T0 + 10, 40, post_id=PID2)
    close(state, T0 + 10)

    assert BoardHeat.from_dict(state.to_dict()) == state


def test_board_heat_to_dict_is_json_serializable():
    data = warmed().to_dict()

    assert BoardHeat.from_dict(json.loads(json.dumps(data))) == BoardHeat.from_dict(data)


# --- Quix 接線 ---


class FakeState:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


def value_of(minute: int, post_id: str = PID) -> dict:
    return comment(minute, post_id=post_id).model_dump(mode="json", by_alias=True)


def test_process_new_state_when_none_stored():
    state = FakeState()

    assert process(value_of(T0), state, CFG, at(T0)) == []
    assert BoardHeat.from_dict(state.data[STATE_KEY]).board_counts == {T0: 1}


def test_process_writes_state_back():
    state = FakeState()
    process(value_of(T0), state, CFG, at(T0))

    process(value_of(T0 + 1), state, CFG, at(T0 + 1))

    assert BoardHeat.from_dict(state.data[STATE_KEY]).watermark == T0 + 1


def test_process_returns_alert_dicts_matching_schema():
    state = FakeState()
    for m in range(T0, T0 + 10):
        process(value_of(m), state, CFG, at(m))

    out = [a for _ in range(40) for a in process(value_of(T0 + 10, PID2), state, CFG, at(T0 + 10))]
    out += process(value_of(T0 + 11), state, CFG, at(T0 + 11))

    alerts = [Alert.model_validate(a) for a in out]
    assert {a.unit_type for a in alerts} == {"post", "board"}
    assert all(a.board == BOARD for a in alerts)


class FakeRegistry:
    pass


class FakeCtx:
    topic = "cdc.public.comments"


def test_deserializer_bad_bytes_raises_decode_error():
    deserializer = CdcCommentDeserializer(FakeRegistry())  # type: ignore[arg-type]

    with pytest.raises(DecodeError):
        deserializer(b"not avro", FakeCtx())  # type: ignore[arg-type]


class FakeDlq:
    def __init__(self) -> None:
        self.published: list[tuple[object, Exception]] = []

    def publish(self, msg, error):
        self.published.append((msg, error))


def test_on_consumer_error_decode_error_goes_to_dlq_and_skips():
    dlq = FakeDlq()
    on_error = make_on_consumer_error(dlq)  # type: ignore[arg-type]
    wrapped = RuntimeError("quix wrapper")
    wrapped.__cause__ = DecodeError("bad")

    assert on_error(wrapped, "msg", logging.getLogger("t")) is True
    assert dlq.published == [("msg", wrapped)]


def test_on_consumer_error_other_error_not_swallowed():
    dlq = FakeDlq()
    on_error = make_on_consumer_error(dlq)  # type: ignore[arg-type]

    assert on_error(RuntimeError("broker down"), "msg", logging.getLogger("t")) is False
    assert on_error(DecodeError("bad"), None, logging.getLogger("t")) is False
    assert dlq.published == []


def test_is_decode_error_follows_cause_chain():
    outer = ValueError("outer")
    outer.__cause__ = KeyError("middle")
    outer.__cause__.__cause__ = DecodeError("inner")

    assert is_decode_error(outer) is True
    assert is_decode_error(ValueError("x")) is False


def test_heat_config_from_settings_copies_all_fields(monkeypatch):
    monkeypatch.setenv("HEAT_MIN_COUNT", "7")
    monkeypatch.setenv("HEAT_EWMA_ALPHA", "0.5")

    config = HeatConfig.from_settings(HeatSettings())

    assert (config.min_count, config.ewma_alpha, config.window_min) == (7, 0.5, 10)


def test_heat_config_post_min_count_defaults_to_80_and_reads_env(monkeypatch):
    assert HeatConfig.from_settings(HeatSettings()).post_min_count == 80

    monkeypatch.setenv("HEAT_POST_MIN_COUNT", "120")

    assert HeatConfig.from_settings(HeatSettings()).post_min_count == 120
