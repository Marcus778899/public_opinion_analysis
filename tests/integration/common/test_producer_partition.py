import time
import uuid

from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from pydantic import BaseModel

from radar.common.kafka.config import admin_config, consumer_config
from radar.common.kafka.producer import JsonProducer
from radar.common.tasks import list_task_partition


class Event(BaseModel):
    board: str


def test_list_tasks_land_in_assigned_partitions(kafka_settings):
    topic = f"it.{uuid.uuid4().hex[:8]}"
    admin = AdminClient(admin_config(kafka_settings))
    admin.create_topics([NewTopic(topic, 3, 1)])[topic].result(30)
    producer = JsonProducer(kafka_settings)
    boards = ["Gossiping", "Stock", "Tech_Job"]

    count = producer.partition_count(topic)
    for b in boards:
        producer.send(topic, b, Event(board=b), partition=list_task_partition(b, boards, count))
    producer.flush()

    consumer = Consumer(consumer_config(kafka_settings, group_id=f"it-{uuid.uuid4().hex[:6]}"))
    try:
        landed = {}
        for p in range(count):
            consumer.assign([TopicPartition(topic, p, 0)])
            # NOTE: 每個 partition 只送了 1 筆，收到就停；沒收到才等到逾時
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                msg = consumer.poll(0.5)
                if msg is not None and msg.error() is None:
                    landed[msg.key().decode()] = msg.partition()
                    break
    finally:
        consumer.close()

    assert count == 3
    assert landed == {"Gossiping": 0, "Stock": 1, "Tech_Job": 2}
