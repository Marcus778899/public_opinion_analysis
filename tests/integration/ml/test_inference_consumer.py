"""推論 consumer 對真實 Kafka（compose 服務）；CdcPost 以 JSON 送出，避開 schema registry。"""

import json
import threading
import uuid
from datetime import UTC, datetime

import pytest
from confluent_kafka import Consumer
from confluent_kafka.admin import AdminClient, NewTopic

from radar.common.kafka.config import admin_config, consumer_config
from radar.common.kafka.consumer import BatchConsumer
from radar.common.kafka.dlq import DLQ_TOPIC, DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.schemas import CdcPost, DlqRecord, Prediction
from radar.ml.inference.main import HashCache, Predictor
from radar.ml.training.train import ModelCard
from tests.unit.ml.fakes import FakeClassifier

TIMEOUT_S = 30
SENTINEL = "Stock.M.1792999999.A.END"


@pytest.fixture(scope="module")
def model() -> tuple[FakeClassifier, ModelCard]:
    card = ModelCard(
        model_version="tfidf-lr-it",
        created_at=datetime.now(UTC),
        dataset="it.jsonl",
        labeler="groq:q",
        label_version="prompt-v6",
        max_chars=2000,
        n_train=6,
        class_counts={"positive": 2, "negative": 2, "neutral": 2},
        params={},
    )
    return FakeClassifier(), card


@pytest.fixture
def topics(kafka_settings) -> tuple[str, str]:
    cdc, out = f"it.cdc.{uuid.uuid4().hex[:8]}", f"it.pred.{uuid.uuid4().hex[:8]}"
    admin = AdminClient(admin_config(kafka_settings))
    futures = admin.create_topics([NewTopic(t, 1, 1) for t in (cdc, out, DLQ_TOPIC)])
    for name, future in futures.items():
        try:
            future.result()
        except Exception:
            if name != DLQ_TOPIC:  # dlq 可能已由其他測試建立
                raise
    return cdc, out


def produce_event(producer: JsonProducer, topic: str, post_id: str, op: str, content: str) -> None:
    value = {"post_id": post_id, "board": "Stock", "title": "t", "content": content, "__op": op}
    producer._producer.produce(topic, key=post_id.encode(), value=json.dumps(value).encode())


def run_inference(kafka_settings, model, cdc: str, out: str, group: str) -> None:
    """跑 consumer 直到處理到 SENTINEL 這篇新文章。"""
    classifier, card = model
    producer = JsonProducer(kafka_settings)
    produce_event(producer, cdc, SENTINEL, "c", "結束")
    producer.flush()
    predictor = Predictor(
        classifier,
        card,
        HashCache(100),
        publish=lambda p: producer.send(out, p.post_id, p),
        flush=producer.flush,
        now=lambda: datetime.now(UTC),
    )
    done = threading.Event()

    def handler(events: list[CdcPost]) -> None:
        predictor(events)
        if any(e.post_id == SENTINEL for e in events):
            done.set()

    consumer = BatchConsumer(
        kafka_settings,
        group_id=group,
        topics=[cdc],
        model=CdcPost,
        handler=handler,
        dlq=DlqPublisher(producer, group),
        batch_size=10,
        batch_timeout_s=0.5,
    )
    thread = threading.Thread(target=consumer.run)
    thread.start()
    finished = done.wait(TIMEOUT_S)
    consumer.stop()
    thread.join(TIMEOUT_S)
    assert finished, "inference consumer did not reach the sentinel event"


def read_all(kafka_settings, topic: str, group: str) -> list[bytes]:
    reader = Consumer(consumer_config(kafka_settings, group))
    reader.subscribe([topic])
    values: list[bytes] = []
    idle = 0
    while idle < 5:
        msg = reader.poll(1.0)
        if msg is None:
            idle += 1
        elif msg.error() is None:
            values.append(msg.value())
    reader.close()
    return values


def predictions(kafka_settings, out: str) -> list[Prediction]:
    return [
        Prediction.model_validate_json(v)
        for v in read_all(kafka_settings, out, f"read-{uuid.uuid4().hex[:6]}")
    ]


def test_new_post_event_produces_prediction(kafka_settings, model, topics):
    cdc, out = topics
    producer = JsonProducer(kafka_settings)
    produce_event(producer, cdc, "Stock.M.1792000001.A.AAA", "c", "好棒 讚")
    producer.flush()

    run_inference(kafka_settings, model, cdc, out, "inf-new")

    got = {p.post_id: p for p in predictions(kafka_settings, out)}
    assert got["Stock.M.1792000001.A.AAA"].model_version == "tfidf-lr-it"
    assert set(got) == {"Stock.M.1792000001.A.AAA", SENTINEL}


def test_push_count_only_update_produces_no_prediction(kafka_settings, model, topics):
    cdc, out = topics
    producer = JsonProducer(kafka_settings)
    produce_event(producer, cdc, "Stock.M.1792000002.A.BBB", "c", "爛 垃圾")
    producer.flush()
    run_inference(kafka_settings, model, cdc, out, "inf-push-1")
    # 再跑一次 = 服務重啟後才收到推噓數更新（快取是空的）
    produce_event(producer, cdc, "Stock.M.1792000002.A.BBB", "u", "爛 垃圾")
    producer.flush()

    run_inference(kafka_settings, model, cdc, out, "inf-push-1")

    ids = [p.post_id for p in predictions(kafka_settings, out)]
    assert ids.count("Stock.M.1792000002.A.BBB") == 1


def test_duplicate_create_event_produces_one_prediction(kafka_settings, model, topics):
    cdc, out = topics
    producer = JsonProducer(kafka_settings)
    for _ in range(2):  # Connect 重啟後重送
        produce_event(producer, cdc, "Stock.M.1792000003.A.CCC", "c", "今天 下雨")
    producer.flush()

    run_inference(kafka_settings, model, cdc, out, "inf-dup")

    ids = [p.post_id for p in predictions(kafka_settings, out)]
    assert ids.count("Stock.M.1792000003.A.CCC") == 1


def test_undecodable_message_lands_in_dlq_and_later_events_still_processed(
    kafka_settings, model, topics
):
    cdc, out = topics
    producer = JsonProducer(kafka_settings)
    producer._producer.produce(cdc, key=b"bad", value=b"not json")
    produce_event(producer, cdc, "Stock.M.1792000004.A.DDD", "c", "好棒 讚")
    producer.flush()

    run_inference(kafka_settings, model, cdc, out, "inf-dlq")

    ids = {p.post_id for p in predictions(kafka_settings, out)}
    assert "Stock.M.1792000004.A.DDD" in ids
    raw = read_all(kafka_settings, DLQ_TOPIC, f"dlq-{cdc}")
    dlq = [DlqRecord.model_validate_json(v) for v in raw]
    assert any(r.source_topic == cdc and r.consumer == "inf-dlq" for r in dlq)
