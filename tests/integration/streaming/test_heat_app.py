"""熱度偵測（Quix）在真的 Kafka 上：暴增產生警示、重啟後不重發、壞訊息進 DLQ（開發規格 7.20）。

schema registry 用 confluent-kafka 的 mock://，Avro schema 與 Debezium 攤平後的欄位相同。
"""

import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext

from radar.common.kafka import names
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.settings import HeatSettings, KafkaSettings
from radar.streaming.heat import build_app

# NOTE: 輸入 topic、group、state 都帶 uuid；alerts、dlq 是固定名稱但斷言只看自己的看板／來源 topic，
# 所以不需要 xdist_group，各測試可以平行
# 閒置多久沒新訊息就停 heat；讀結果時收到預期筆數後再多等的秒數
IDLE_S = 5
SETTLE_S = 1.5
NO_RESULT_WAIT_S = 4

SCHEMA = json.dumps(
    {
        "type": "record",
        "name": "Value",
        "namespace": "cdc.public.comments",
        "fields": [
            {"name": "post_id", "type": "string"},
            {"name": "floor", "type": "int"},
            {"name": "type", "type": "string"},
            {"name": "user_id", "type": ["null", "string"], "default": None},
            {"name": "content", "type": ["null", "string"], "default": None},
            {"name": "commented_at", "type": ["null", "string"], "default": None},
            {"name": "__op", "type": ["null", "string"], "default": None},
            {"name": "__source_ts_ms", "type": ["null", "long"], "default": None},
            {"name": "__source_lsn", "type": ["null", "long"], "default": None},
            {"name": "__deleted", "type": ["null", "string"], "default": None},
        ],
    }
)


@pytest.fixture(scope="module")
def kafka(kafka_settings):
    # NOTE: alerts 已由 session 重置建好（ClickHouse 訂閱用）；dlq 由本模組建立
    admin = AdminClient({"bootstrap.servers": kafka_settings.bootstrap_servers})
    futures = admin.create_topics(
        [NewTopic(t, num_partitions=1, replication_factor=1) for t in (names.ALERTS, names.DLQ)]
    )
    for f in futures.values():
        try:
            f.result(30)
        except KafkaException as e:
            if e.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise
    return kafka_settings


@pytest.fixture
def registry():
    return SchemaRegistryClient.new_client({"url": f"mock://{uuid.uuid4().hex}"})


@pytest.fixture
def run(kafka, registry, tmp_path):
    """建立輸入 topic，回傳 run_app(state_dir, idle_s)：跑 heat 直到 idle_s 秒沒有新訊息。"""
    topic = f"it.comments.{uuid.uuid4().hex[:8]}"
    group = f"heat-{uuid.uuid4().hex[:8]}"
    admin = AdminClient({"bootstrap.servers": kafka.bootstrap_servers})
    # NOTE: 單一 partition，事件順序才固定；多 partition 時舊事件可能晚到而超過寬限
    admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])[topic].result(30)

    def run_app(state_dir, idle_s: float) -> None:
        settings = HeatSettings(
            input_topic=topic,
            consumer_group=group,
            state_dir=state_dir,
            warmup_min=5,
            # NOTE: 暴增只有 40 則；這裡測的是串接與 exactly-once，不是門檻（#59）
            post_min_count=30,
        )
        producer = JsonProducer(kafka)
        app = build_app(settings, kafka, DlqPublisher(producer, group), registry)
        # NOTE: Quix 會註冊 signal handler，只能在 main thread 跑；timeout 是「多久沒新訊息就停」
        app.run(timeout=idle_s, collect=False)
        producer.flush()

    run_app.topic = topic  # type: ignore[attr-defined]
    return run_app


def produce(kafka: KafkaSettings, registry, topic: str, events: list[dict]) -> None:
    serializer = AvroSerializer(registry, SCHEMA)
    ctx = SerializationContext(topic, MessageField.VALUE)
    producer = Producer({"bootstrap.servers": kafka.bootstrap_servers})
    for event in events:
        producer.produce(topic, key=str(event["post_id"]).encode(), value=serializer(event, ctx))
    producer.flush(30)


def board_name(prefix: str) -> str:
    """alerts topic 跨次測試保留，看板名稱帶 uuid，才不會讀到上次的警示。"""
    return f"{prefix}{uuid.uuid4().hex[:6]}"


def comment(post_id: str, floor: int, at: datetime, op: str = "c") -> dict:
    return {
        "post_id": post_id,
        "floor": floor,
        "type": "push",
        "user_id": "u",
        "content": "c",
        "commented_at": at.isoformat().replace("+00:00", "Z"),
        "__op": op,
        "__source_ts_ms": int(at.timestamp() * 1000),
        "__source_lsn": 0,
        "__deleted": "false",
    }


def baseline_and_surge(board: str, now: datetime) -> list[dict]:
    quiet, hot = f"{board}.M.1792000000.A.AAA", f"{board}.M.1792000001.A.BBB"
    events = [comment(quiet, i, now - timedelta(minutes=30 - i)) for i in range(28)]
    # 暴增都在同一分鐘內，結算時的 value 才確定是 40
    minute = now.replace(second=0, microsecond=0)
    events += [comment(hot, 100 + i, minute + timedelta(seconds=i)) for i in range(40)]
    # NOTE: 分鐘要等下一分鐘的推文進來才結算（#50），最後送一則讓暴增的分鐘結算
    events.append(comment(quiet, 99, minute + timedelta(seconds=90)))
    return events


def read_matching(
    kafka: KafkaSettings,
    topic: str,
    matches: Callable[[bytes], bool],
    expected: int,
    max_s: float = 20,
) -> list[bytes]:
    """收到 expected 筆符合的訊息後再多等 SETTLE_S（抓多送的）；expected 為 0 時等固定秒數。"""
    consumer = Consumer(
        {
            "bootstrap.servers": kafka.bootstrap_servers,
            "group.id": f"reader-{uuid.uuid4().hex}",
            "auto.offset.reset": "earliest",
            # NOTE: 只讀已 commit 的 transaction，未 commit 的警示不算
            "isolation.level": "read_committed",
        }
    )
    consumer.subscribe([topic])
    values: list[bytes] = []
    start = time.monotonic()
    reached_at = start if expected == 0 else None
    while time.monotonic() - start < max_s:
        msg = consumer.poll(0.5)
        if msg is not None and not msg.error() and matches(msg.value()):
            values.append(msg.value())
            if len(values) >= expected and reached_at is None:
                reached_at = time.monotonic()
        wait = NO_RESULT_WAIT_S if expected == 0 else SETTLE_S
        if reached_at is not None and time.monotonic() - reached_at >= wait:
            break
    consumer.close()
    return values


def alerts_for(kafka: KafkaSettings, board: str, expected: int) -> list[dict]:
    def is_board(value: bytes) -> bool:
        return json.loads(value)["board"] == board

    return [json.loads(v) for v in read_matching(kafka, names.ALERTS, is_board, expected)]


def test_surge_produces_one_alert_per_unit(kafka, registry, run, tmp_path):
    now = datetime.now(UTC)
    board = board_name("HeatA")
    produce(kafka, registry, run.topic, baseline_and_surge(board, now))

    run(tmp_path / "state", IDLE_S)

    alerts = alerts_for(kafka, board, 2)
    assert sorted(a["unit_type"] for a in alerts) == ["board", "post"]
    post = next(a for a in alerts if a["unit_type"] == "post")
    assert post["unit_key"] == f"{board}.M.1792000001.A.BBB"
    assert post["value"] == 40  # 結算時的值，不是剛越過門檻的 30


def test_updates_and_deletes_produce_no_alert(kafka, registry, run, tmp_path):
    now = datetime.now(UTC)
    board = board_name("HeatB")
    events = baseline_and_surge(board, now)
    for event in events[28:]:
        event["__op"] = "u"  # 樓層位移的改寫，不算新增推文
    produce(kafka, registry, run.topic, events)

    run(tmp_path / "state", IDLE_S)

    assert alerts_for(kafka, board, 0) == []


def test_restart_restores_state_and_does_not_realert(kafka, registry, run, tmp_path):
    now = datetime.now(UTC)
    board = board_name("HeatC")
    produce(kafka, registry, run.topic, baseline_and_surge(board, now))
    run(tmp_path / "first", IDLE_S)
    assert len(alerts_for(kafka, board, 2)) == 2

    hot = f"{board}.M.1792000001.A.BBB"
    more = [comment(hot, 500 + i, now + timedelta(minutes=1, seconds=i)) for i in range(40)]
    more.append(comment(hot, 600, now + timedelta(minutes=3)))
    produce(kafka, registry, run.topic, more)
    # 新的 state 目錄：state 只能從 changelog topic 恢復；冷卻期間不應再發
    run(tmp_path / "second", IDLE_S)

    assert len(alerts_for(kafka, board, 2)) == 2


def test_undecodable_message_lands_in_dlq_and_processing_continues(kafka, registry, run, tmp_path):
    now = datetime.now(UTC)
    board = board_name("HeatD")
    producer = Producer({"bootstrap.servers": kafka.bootstrap_servers})
    producer.produce(run.topic, key=b"x", value=b"not avro")
    producer.flush(30)
    produce(kafka, registry, run.topic, baseline_and_surge(board, now))

    run(tmp_path / "state", IDLE_S)

    def from_topic(value: bytes) -> bool:
        return json.loads(value)["source_topic"] == run.topic

    assert read_matching(kafka, names.DLQ, from_topic, 1)
    assert len(alerts_for(kafka, board, 2)) == 2
