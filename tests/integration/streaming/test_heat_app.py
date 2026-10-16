"""熱度偵測（Quix）在真的 Kafka 上：暴增產生警示、重啟後不重發、壞訊息進 DLQ（開發規格 7.20）。

schema registry 用 confluent-kafka 的 mock://，Avro schema 與 Debezium 攤平後的欄位相同。
"""

import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext
from testcontainers.community.kafka import KafkaContainer

from radar.common.kafka import names
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.settings import HeatSettings, KafkaSettings
from radar.streaming.heat import build_app

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
def kafka():
    # NOTE: exactly-once 需要 transaction；單節點要把 transaction log 的副本數降成 1
    container = (
        KafkaContainer()
        .with_kraft()
        .with_env("KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR", "1")
        .with_env("KAFKA_TRANSACTION_STATE_LOG_MIN_ISR", "1")
    )
    with container:
        settings = KafkaSettings(bootstrap_servers=container.get_bootstrap_server(), client_id="it")
        admin = AdminClient({"bootstrap.servers": settings.bootstrap_servers})
        futures = admin.create_topics(
            [NewTopic(t, num_partitions=1, replication_factor=1) for t in (names.ALERTS, names.DLQ)]
        )
        for f in futures.values():
            f.result(30)
        yield settings


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
            input_topic=topic, consumer_group=group, state_dir=state_dir, warmup_min=5
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
    events += [comment(hot, 100 + i, now - timedelta(seconds=40 - i)) for i in range(40)]
    return events


def read_all(kafka: KafkaSettings, topic: str) -> list[bytes]:
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
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        msg = consumer.poll(1)
        if msg is not None and not msg.error():
            values.append(msg.value())
    consumer.close()
    return values


def alerts_for(kafka: KafkaSettings, board: str) -> list[dict]:
    alerts = [json.loads(v) for v in read_all(kafka, names.ALERTS)]
    return [a for a in alerts if a["board"] == board]


def test_surge_produces_one_alert_per_unit(kafka, registry, run, tmp_path):
    now = datetime.now(UTC)
    produce(kafka, registry, run.topic, baseline_and_surge("HeatA", now))

    run(tmp_path / "state", 25)

    alerts = alerts_for(kafka, "HeatA")
    assert sorted(a["unit_type"] for a in alerts) == ["board", "post"]
    post = next(a for a in alerts if a["unit_type"] == "post")
    assert post["unit_key"] == "HeatA.M.1792000001.A.BBB"
    assert post["value"] >= 30


def test_updates_and_deletes_produce_no_alert(kafka, registry, run, tmp_path):
    now = datetime.now(UTC)
    events = baseline_and_surge("HeatB", now)
    for event in events[28:]:
        event["__op"] = "u"  # 樓層位移的改寫，不算新增推文
    produce(kafka, registry, run.topic, events)

    run(tmp_path / "state", 20)

    assert alerts_for(kafka, "HeatB") == []


def test_restart_restores_state_and_does_not_realert(kafka, registry, run, tmp_path):
    now = datetime.now(UTC)
    produce(kafka, registry, run.topic, baseline_and_surge("HeatC", now))
    run(tmp_path / "first", 25)
    assert len(alerts_for(kafka, "HeatC")) == 2

    hot = "HeatC.M.1792000001.A.BBB"
    more = [comment(hot, 500 + i, now + timedelta(seconds=i)) for i in range(40)]
    produce(kafka, registry, run.topic, more)
    # 新的 state 目錄：state 只能從 changelog topic 恢復；冷卻期間不應再發
    run(tmp_path / "second", 25)

    assert len(alerts_for(kafka, "HeatC")) == 2


def test_undecodable_message_lands_in_dlq_and_processing_continues(kafka, registry, run, tmp_path):
    now = datetime.now(UTC)
    producer = Producer({"bootstrap.servers": kafka.bootstrap_servers})
    producer.produce(run.topic, key=b"x", value=b"not avro")
    producer.flush(30)
    produce(kafka, registry, run.topic, baseline_and_surge("HeatD", now))

    run(tmp_path / "state", 25)

    dlq = [json.loads(v) for v in read_all(kafka, names.DLQ)]
    assert any(r["source_topic"] == run.topic for r in dlq)
    assert len(alerts_for(kafka, "HeatD")) == 2
