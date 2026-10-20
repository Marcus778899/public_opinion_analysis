import base64
from datetime import UTC, datetime, timedelta

import pytest

from radar.common.kafka import names
from radar.common.schemas import CdcComment
from radar.streaming.replay import (
    RecordedMessage,
    read_file,
    record,
    replay,
    replay_delays,
    surge_events,
    write_file,
)

PID = "Stock.M.1792000000.A.ABC"
NOW = datetime(2026, 10, 17, 3, 0, tzinfo=UTC)


def msg(ts: int, value: bytes | None = b"v", key: bytes | None = b"k") -> RecordedMessage:
    enc = lambda b: base64.b64encode(b).decode() if b is not None else None  # noqa: E731
    return RecordedMessage(ts, enc(key), enc(value))


# --- RecordedMessage ---


def test_recorded_message_json_roundtrip():
    m = msg(1000, b"\x00\x01avro", b"key")

    back = RecordedMessage.from_json(m.to_json())

    assert back == m
    assert (back.key(), back.value()) == (b"key", b"\x00\x01avro")


def test_recorded_message_null_key_roundtrip():
    m = msg(1000, key=None)

    assert RecordedMessage.from_json(m.to_json()).key() is None


def test_recorded_message_bad_base64_rejected():
    with pytest.raises(ValueError, match="bad recorded message"):
        RecordedMessage.from_json('{"timestamp_ms": 1, "key_b64": null, "value_b64": "!!"}')


def test_recorded_message_missing_field_rejected():
    with pytest.raises(ValueError, match="bad recorded message"):
        RecordedMessage.from_json('{"timestamp_ms": 1}')


# --- replay_delays ---


def test_replay_delays_first_message_zero():
    assert replay_delays([msg(5000)], 1.0) == [0]


def test_replay_delays_divided_by_speed():
    assert replay_delays([msg(0), msg(2000), msg(6000)], 2.0) == [0, 1.0, 2.0]


def test_replay_delays_non_positive_speed_rejected():
    with pytest.raises(ValueError, match="speed"):
        replay_delays([msg(0)], 0)


def test_replay_delays_out_of_order_timestamps_clamped_to_zero():
    assert replay_delays([msg(5000), msg(3000), msg(6000)], 1.0) == [0, 0, 1.0]


# --- replay / record（fake producer、consumer）---


class FakeProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes | None, bytes | None]] = []
        self.flushed = 0

    def produce(self, topic, key=None, value=None):
        self.sent.append((topic, key, value))

    def poll(self, _timeout):
        return 0

    def flush(self, *_args):
        self.flushed += 1
        return 0


def test_replay_sends_bytes_unchanged_to_replay_topic():
    producer = FakeProducer()
    slept: list[float] = []

    n = replay(producer, [msg(0, b"a"), msg(1000, b"b")], 1.0, slept.append)  # type: ignore[arg-type]

    assert n == 2
    assert producer.sent == [
        (names.REPLAY_COMMENTS, b"k", b"a"),
        (names.REPLAY_COMMENTS, b"k", b"b"),
    ]
    assert slept == [1.0]


def test_replay_flushes_after_sending():
    producer = FakeProducer()

    replay(producer, [msg(0)], 1.0, lambda _s: None)  # type: ignore[arg-type]

    assert producer.flushed == 1


class FakeTP:
    def __init__(self, partition: int, offset: int) -> None:
        self.partition, self.offset = partition, offset


class FakeMessage:
    def __init__(self, partition: int, offset: int, ts: int, value: bytes) -> None:
        self._p, self._o, self._ts, self._v = partition, offset, ts, value

    def error(self):
        return None

    def partition(self):
        return self._p

    def offset(self):
        return self._o

    def timestamp(self):
        return (1, self._ts)

    def key(self):
        return None

    def value(self):
        return self._v


class FakeConsumer:
    """兩個 partition：p0 有 3 則（第 3 則超過 until），p1 有 1 則。"""

    def __init__(self, messages: list[FakeMessage], ends: dict[int, int]) -> None:
        self._messages = list(messages)
        self._ends = ends
        self.assigned: list[int] = []

    def list_topics(self, topic, timeout):
        partitions = {p: None for p in self._ends}

        class Meta:
            topics = {topic: type("T", (), {"partitions": partitions})()}

        return Meta()

    def offsets_for_times(self, tps, timeout):
        return [FakeTP(tp.partition, 0) for tp in tps]

    def get_watermark_offsets(self, tp, timeout):
        return (0, self._ends[tp.partition])

    def assign(self, tps):
        self.assigned = [tp.partition for tp in tps]

    def poll(self, _timeout):
        return self._messages.pop(0) if self._messages else None


def test_record_stops_at_until():
    until = datetime.fromtimestamp(10, UTC)
    consumer = FakeConsumer(
        [
            FakeMessage(0, 0, 1000, b"a"),
            FakeMessage(0, 1, 9000, b"b"),
            FakeMessage(0, 2, 11000, b"c"),
        ],
        {0: 3},
    )

    out = list(record(consumer, "t", NOW - timedelta(days=1), until))  # type: ignore[arg-type]

    assert [m.value() for m in out] == [b"a", b"b"]


def test_record_reads_all_partitions():
    consumer = FakeConsumer(
        [FakeMessage(0, 0, 1000, b"a"), FakeMessage(1, 0, 2000, b"b")], {0: 1, 1: 1}
    )

    out = list(record(consumer, "t", NOW - timedelta(days=1), NOW))  # type: ignore[arg-type]

    assert sorted(m.value() for m in out) == [b"a", b"b"]
    assert sorted(consumer.assigned) == [0, 1]


def test_record_skips_empty_partitions():
    consumer = FakeConsumer([], {0: 0})

    assert list(record(consumer, "t", NOW, NOW)) == []  # type: ignore[arg-type]
    assert consumer.assigned == []


# --- surge_events ---


def test_surge_events_count_and_floors():
    events = surge_events(PID, 500, 4, 2, NOW)

    assert [e["floor"] for e in events] == [500, 501, 502, 503]


def test_surge_events_spread_over_minutes():
    events = [CdcComment.model_validate(e) for e in surge_events(PID, 1, 4, 2, NOW)]

    times = [e.commented_at for e in events]
    assert times[0] == NOW - timedelta(seconds=90)
    assert times[-1] == NOW
    assert times == sorted(times)


def test_surge_events_parse_as_cdc_comment_create():
    [event] = surge_events(PID, 1, 1, 1, NOW)
    c = CdcComment.model_validate(event)

    assert (c.post_id, c.op, c.deleted, c.source_ts_ms) == (
        PID,
        "c",
        "false",
        int(NOW.timestamp() * 1000),
    )


@pytest.mark.parametrize(("post_id", "count", "minutes"), [("bad", 1, 1), (PID, 0, 1), (PID, 1, 0)])
def test_surge_events_invalid_input_rejected(post_id, count, minutes):
    with pytest.raises(ValueError):
        surge_events(post_id, 1, count, minutes, NOW)


# --- 檔案 ---


def test_write_then_read_file_roundtrip(tmp_path):
    path = tmp_path / "sub" / "x.jsonl"
    messages = [msg(1), msg(2, key=None)]

    assert write_file(path, iter(messages)) == 2
    assert read_file(path) == messages


def test_read_file_bad_line_reports_line_number(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text(msg(1).to_json() + "\nnot json\n")

    with pytest.raises(ValueError, match=r"x.jsonl:2"):
        read_file(path)
