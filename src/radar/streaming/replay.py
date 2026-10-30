"""[一次性] 熱度偵測的錄製、回放與人工暴增（S5-05，開發規格 7.20）。

用法（前綴 `uv run --env-file .env`，才讀得到 KAFKA_BOOTSTRAP_SERVERS）：
  python -m radar.streaming.replay record --since <ISO> --until <ISO> --out data/replay/x.jsonl
  python -m radar.streaming.replay replay --file data/replay/x.jsonl [--speed 10]
  python -m radar.streaming.replay surge --post-id <post_id> [--count N] --minutes 3
（--count 預設 HEAT_POST_MIN_COUNT；完整步驟見開發規格 7.20）
"""

import argparse
import base64
import binascii
import json
import math
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from confluent_kafka import Consumer, KafkaException, Producer, TopicPartition
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext
from pydantic import ValidationError

from radar.common.cli import ENV_FILE_HINT, fail, missing_env_names
from radar.common.ids import split_post_id
from radar.common.kafka import names
from radar.common.kafka.config import consumer_config, producer_config
from radar.common.log import log, setup_logging
from radar.common.settings import (
    HeatSettings,
    KafkaSettings,
    SchemaRegistrySettings,
    get_kafka_settings,
)

# NOTE: 回放與人工暴增一律送到 REPLAY_COMMENTS，不碰正式的 cdc.public.comments
SCHEMA_SUBJECT = f"{names.CDC_COMMENTS}-value"
POLL_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class RecordedMessage:
    """一則原始訊息；key、value 是 base64，時間是 Kafka 的 timestamp（毫秒）。"""

    timestamp_ms: int
    key_b64: str | None
    value_b64: str | None

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, line: str) -> "RecordedMessage":
        data = json.loads(line)
        try:
            msg = cls(int(data["timestamp_ms"]), data["key_b64"], data["value_b64"])
            msg.key()
            msg.value()
        except (KeyError, TypeError, binascii.Error) as e:
            raise ValueError(f"bad recorded message: {e}") from e
        return msg

    def key(self) -> bytes | None:
        return _decode(self.key_b64)

    def value(self) -> bytes | None:
        return _decode(self.value_b64)


def _encode(raw: bytes | None) -> str | None:
    return base64.b64encode(raw).decode() if raw is not None else None


def _decode(text: str | None) -> bytes | None:
    return base64.b64decode(text, validate=True) if text is not None else None


def record(
    consumer: Consumer, topic: str, since: datetime, until: datetime
) -> Iterator[RecordedMessage]:
    """各 partition 從 offsets_for_times(since) 讀到 until 或結尾為止。"""
    until_ms = int(until.timestamp() * 1000)
    partitions = consumer.list_topics(topic, timeout=10).topics[topic].partitions
    starts = consumer.offsets_for_times(
        [TopicPartition(topic, p, int(since.timestamp() * 1000)) for p in partitions], timeout=10
    )
    ends = {
        p: consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=10)[1]
        for p in partitions
    }
    # offset < 0 代表 since 之後沒有訊息
    pending = {tp.partition for tp in starts if 0 <= tp.offset < ends[tp.partition]}
    consumer.assign([tp for tp in starts if tp.partition in pending])
    while pending:
        msg = consumer.poll(POLL_TIMEOUT_S)
        if msg is None:
            break
        if msg.error():
            continue
        partition, ts = msg.partition(), msg.timestamp()[1]
        if partition not in pending:
            continue
        if ts > until_ms:
            pending.discard(partition)
            continue
        yield RecordedMessage(ts, _encode(msg.key()), _encode(msg.value()))
        if msg.offset() >= ends[partition] - 1:
            pending.discard(partition)


def replay_delays(messages: list[RecordedMessage], speed: float) -> list[float]:
    """純函式：每則訊息送出前要等的秒數（與上一則的時間差 / speed）；時間倒退的不等。"""
    if speed <= 0:
        raise ValueError("speed must be positive")
    delays: list[float] = []
    latest: int | None = None
    for msg in messages:
        gap = 0 if latest is None else max(0, msg.timestamp_ms - latest)
        delays.append(gap / 1000 / speed)
        latest = msg.timestamp_ms if latest is None else max(latest, msg.timestamp_ms)
    return delays


def replay(
    producer: Producer,
    messages: list[RecordedMessage],
    speed: float,
    sleep: Callable[[float], None],
) -> int:
    """依原本的間隔把 bytes 原封不動送到 REPLAY_COMMENTS；回傳送出的則數。"""
    for msg, delay in zip(messages, replay_delays(messages, speed), strict=True):
        if delay > 0:
            sleep(delay)
        producer.produce(names.REPLAY_COMMENTS, key=msg.key(), value=msg.value())
        producer.poll(0)
    producer.flush()
    return len(messages)


def surge_events(
    post_id: str, start_floor: int, count: int, minutes: int, now: datetime
) -> list[dict[str, object]]:
    """純函式：人工暴增的推文 CDC 事件（op=c、push），commented_at 平均分散在 minutes 分鐘內。"""
    split_post_id(post_id)
    if count <= 0 or minutes <= 0:
        raise ValueError("count and minutes must be positive")
    start = now - timedelta(minutes=minutes)
    step = timedelta(minutes=minutes) / count
    events: list[dict[str, object]] = []
    for i in range(count):
        commented_at = start + step * (i + 1)
        events.append(
            {
                "post_id": post_id,
                "floor": start_floor + i,
                "type": "push",
                "user_id": "surge",
                "content": "人工暴增（S5-05）",
                # Debezium 的 timestamptz 是 ISO 8601 字串（設計文件 6.2）
                "commented_at": commented_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "__op": "c",
                "__source_ts_ms": int(commented_at.timestamp() * 1000),
                "__source_lsn": 0,
                "__deleted": "false",
            }
        )
    return events


def surge_tail_event(post_id: str, floor: int, last: datetime) -> dict[str, object]:
    """暴增結束後 1 分鐘的單筆事件；回放 topic 沒有後續事件，最後一分鐘才會被結算。"""
    at = last + timedelta(minutes=1)
    return {
        "post_id": post_id,
        "floor": floor,
        "type": "push",
        "user_id": "surge",
        "content": "人工暴增收尾（S5-05）",
        "commented_at": at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "__op": "c",
        "__source_ts_ms": int(at.timestamp() * 1000),
        "__source_lsn": 0,
        "__deleted": "false",
    }


def surge(
    producer: Producer,
    registry: SchemaRegistryClient,
    events: list[dict[str, object]],
) -> int:
    """用 Apicurio 上 SCHEMA_SUBJECT 的最新 schema 序列化並送到 REPLAY_COMMENTS。"""
    serializer = AvroSerializer(
        registry,
        conf={
            "auto.register.schemas": False,
            "use.latest.version": True,
            # NOTE: 送到回放 topic，但 schema 要用正式 topic 的，才和 Debezium 的格式相同
            "subject.name.strategy": lambda _ctx, _name: SCHEMA_SUBJECT,
        },
    )
    ctx = SerializationContext(names.REPLAY_COMMENTS, MessageField.VALUE)
    for event in events:
        producer.produce(
            names.REPLAY_COMMENTS, key=str(event["post_id"]).encode(), value=serializer(event, ctx)
        )
        producer.poll(0)
    producer.flush()
    return len(events)


def write_file(path: Path, messages: Iterator[RecordedMessage]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w") as f:
        for msg in messages:
            f.write(msg.to_json() + "\n")
            n += 1
    return n


def read_file(path: Path) -> list[RecordedMessage]:
    messages: list[RecordedMessage] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            messages.append(RecordedMessage.from_json(line))
        except ValueError as e:  # json.JSONDecodeError 也是 ValueError
            raise ValueError(f"{path}:{lineno}: {e}") from e
    return messages


def parse_time(text: str) -> datetime:
    """帶時區的 ISO 8601 時間；沒帶時區會被當成本機時間而錄錯範圍，所以直接拒絕。"""
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"'{text}' 不是 ISO 8601 時間，例 2026-10-30T02:30:00+00:00"
        ) from None
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(f"'{text}' 沒有時區，請加上，例 +00:00 代表 UTC")
    return parsed


def positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' 不是整數") from None
    if value <= 0:
        raise argparse.ArgumentTypeError(f"'{text}' 必須大於 0")
    return value


def positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' 不是數字") from None
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"'{text}' 必須大於 0")
    return value


def post_id_arg(text: str) -> str:
    try:
        split_post_id(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"'{text}' 不是 post_id，格式 <board>.<檔名>，例 Gossiping.M.1792058026.A.0AE"
        ) from None
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m radar.streaming.replay",
        description="熱度偵測的錄製、回放與人工暴增（S5-05，步驟見開發規格 7.20）。"
        f"要用 `{ENV_FILE_HINT}` 執行，才讀得到 KAFKA_BOOTSTRAP_SERVERS。",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="{record,replay,surge}")
    rec = sub.add_parser("record", help="把正式 cdc.public.comments 某段時間的訊息存成檔案（唯讀）")
    rec.add_argument(
        "--since",
        type=parse_time,
        required=True,
        help="起點，帶時區的 ISO 8601，例 2026-10-30T02:30:00+00:00",
    )
    rec.add_argument(
        "--until", type=parse_time, required=True, help="終點（含），格式同 --since，要晚於 --since"
    )
    rec.add_argument(
        "--out", type=Path, required=True, help="輸出的 JSONL 檔，例 data/replay/x.jsonl"
    )
    rep = sub.add_parser(
        "replay", help="把錄好的檔案依原間隔重送到 replay.cdc.comments（用來暖機）"
    )
    rep.add_argument("--file", type=Path, required=True, help="record 產生的 JSONL 檔")
    rep.add_argument(
        "--speed",
        type=positive_float,
        default=1.0,
        help="加速倍數，大於 0；預設 1（原速），暖機常用 1000",
    )
    sg = sub.add_parser("surge", help="對指定文章人工製造推文暴增，送到 replay.cdc.comments")
    sg.add_argument(
        "--post-id",
        type=post_id_arg,
        required=True,
        help="暴增的文章，例 Gossiping.M.1792058026.A.0AE",
    )
    sg.add_argument(
        "--count",
        type=positive_int,
        default=None,
        help="推文則數；預設 HEAT_POST_MIN_COUNT（文章警示門檻）",
    )
    sg.add_argument("--minutes", type=positive_int, default=3, help="暴增分散在幾分鐘內，預設 3")
    sg.add_argument("--start-floor", type=int, default=10_000, help="第一則的樓層號，預設 10000")
    return parser


def kafka_settings_or_fail() -> KafkaSettings:
    try:
        return get_kafka_settings()
    except ValidationError as exc:
        missing = missing_env_names(exc, "KAFKA_")
        if not missing:
            raise
        fail(f"缺少環境變數 {', '.join(missing)}；請用 `{ENV_FILE_HINT}` 執行以載入 .env")


def replay_topic_has_messages(consumer: Consumer) -> bool:
    """replay.cdc.comments 是否還留著舊訊息（任一 partition 的結尾大於開頭）。"""
    topic = names.REPLAY_COMMENTS
    partitions = consumer.list_topics(topic, timeout=10).topics[topic].partitions
    marks = (
        consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=10) for p in partitions
    )
    return any(high > low for low, high in marks)


def warn_if_replay_topic_dirty(kafka: KafkaSettings) -> None:
    """舊訊息會被新的 consumer group 一起讀入，時間較早的新資料被當遲到丟掉（7.20）。"""
    consumer = Consumer(consumer_config(kafka, "replay-check"))
    try:
        dirty = replay_topic_has_messages(consumer)
    except KafkaException as e:
        log.warning("cannot check %s: %s", names.REPLAY_COMMENTS, e)
        return
    finally:
        consumer.close()
    if dirty:
        log.warning(
            "%s still has old messages; a new heat group reads them too and drops "
            "earlier-timed replay data as late. Delete and recreate the topic first (spec 7.20)",
            names.REPLAY_COMMENTS,
        )


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("replay")
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "record" and args.since > args.until:
        parser.error("--since 必須早於 --until")
    messages: list[RecordedMessage] = []
    if args.command == "replay":
        try:
            messages = read_file(args.file)
        except (OSError, ValueError) as e:
            fail(f"讀不了 {args.file}：{e}")
    kafka = kafka_settings_or_fail()
    if args.command == "record":
        consumer = Consumer(consumer_config(kafka, "replay-record"))
        try:
            n = write_file(args.out, record(consumer, names.CDC_COMMENTS, args.since, args.until))
        finally:
            consumer.close()
        log.info("recorded %d messages to %s", n, args.out)
        return
    warn_if_replay_topic_dirty(kafka)
    producer = Producer(producer_config(kafka))
    if args.command == "replay":
        n = replay(producer, messages, args.speed, time.sleep)
    else:
        registry = SchemaRegistryClient.new_client({"url": SchemaRegistrySettings().url})
        now = datetime.now(UTC)
        count = args.count if args.count is not None else HeatSettings().post_min_count
        events = surge_events(args.post_id, args.start_floor, count, args.minutes, now)
        events.append(surge_tail_event(args.post_id, args.start_floor + count, now))
        n = surge(producer, registry, events)
    log.info("sent %d messages to %s", n, names.REPLAY_COMMENTS)


if __name__ == "__main__":
    main()
