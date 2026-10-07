import threading
import uuid

import pytest
from confluent_kafka import Consumer
from confluent_kafka.admin import AdminClient, NewTopic
from pydantic import BaseModel

from radar.common.kafka.config import admin_config, consumer_config
from radar.common.kafka.consumer import BatchConsumer
from radar.common.kafka.dlq import DLQ_TOPIC, DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.schemas import DlqRecord

TIMEOUT_S = 30


class Event(BaseModel):
    id: int


@pytest.fixture
def topic(kafka_settings):
    name = f"it.{uuid.uuid4().hex[:8]}"
    admin = AdminClient(admin_config(kafka_settings))
    futures = admin.create_topics([NewTopic(name, 1, 1), NewTopic(DLQ_TOPIC, 1, 1)])
    for t, f in futures.items():
        try:
            f.result()
        except Exception:
            if t != DLQ_TOPIC:  # dlq 可能已由其他測試建立
                raise
    return name


def make_consumer(settings, topic, group, handler, producer):
    return BatchConsumer(
        settings,
        group_id=group,
        topics=[topic],
        model=Event,
        handler=handler,
        dlq=DlqPublisher(producer, group),
        batch_size=10,
        batch_timeout_s=0.5,
    )


def run_until(consumer, done: threading.Event):
    """在背景執行緒跑 consumer，等 done 或逾時後停止並回傳 run() 拋出的例外。"""
    errors: list[BaseException] = []

    def target():
        try:
            consumer.run()
        except BaseException as e:
            errors.append(e)
            done.set()

    thread = threading.Thread(target=target)
    thread.start()
    finished = done.wait(TIMEOUT_S)
    consumer.stop()
    thread.join(TIMEOUT_S)
    assert finished, "consumer did not finish in time"
    return errors


def test_producer_to_batch_consumer_roundtrip(kafka_settings, topic):
    producer = JsonProducer(kafka_settings)
    for i in range(5):
        producer.send(topic, f"k{i}", Event(id=i))
    producer.flush()
    received: list[Event] = []
    done = threading.Event()

    def handler(items):
        received.extend(items)
        if len(received) >= 5:
            done.set()

    errors = run_until(make_consumer(kafka_settings, topic, "g1", handler, producer), done)

    assert errors == []
    assert sorted(e.id for e in received) == [0, 1, 2, 3, 4]


def test_poison_message_lands_in_dlq(kafka_settings, topic):
    producer = JsonProducer(kafka_settings)
    producer._producer.produce(topic, key=b"bad", value=b"not json")
    producer.send(topic, "good", Event(id=1))
    producer.flush()
    done = threading.Event()

    errors = run_until(
        make_consumer(kafka_settings, topic, "g2", lambda items: done.set(), producer), done
    )

    assert errors == []
    dlq_reader = Consumer(consumer_config(kafka_settings, f"dlq-{topic}"))
    dlq_reader.subscribe([DLQ_TOPIC])
    records = []
    for _ in range(20):
        msg = dlq_reader.poll(1.0)
        if msg is not None and msg.error() is None:
            records.append(DlqRecord.model_validate_json(msg.value()))
        if any(r.source_topic == topic for r in records):
            break
    dlq_reader.close()
    assert any(r.source_topic == topic and r.consumer == "g2" for r in records)


def test_redelivered_after_restart_when_not_committed(kafka_settings, topic):
    producer = JsonProducer(kafka_settings)
    producer.send(topic, "k", Event(id=7))
    producer.flush()
    first_done = threading.Event()

    def crash(items):
        first_done.set()
        raise RuntimeError("crash before commit")

    errors = run_until(make_consumer(kafka_settings, topic, "g3", crash, producer), first_done)
    assert isinstance(errors[0], RuntimeError)

    received: list[Event] = []
    second_done = threading.Event()

    def collect(items):
        received.extend(items)
        second_done.set()

    run_until(make_consumer(kafka_settings, topic, "g3", collect, producer), second_done)

    assert received == [Event(id=7)]
