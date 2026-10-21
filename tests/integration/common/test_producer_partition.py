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


def _topic_ready(admin: AdminClient, topic: str, partitions: int) -> bool:
    meta = admin.list_topics(topic, timeout=10).topics.get(topic)
    if meta is None or meta.error is not None or len(meta.partitions) != partitions:
        return False
    return all(p.leader >= 0 and p.error is None for p in meta.partitions.values())


def test_list_tasks_land_in_assigned_partitions(kafka_settings, wait_until):
    topic = f"it.{uuid.uuid4().hex[:8]}"
    admin = AdminClient(admin_config(kafka_settings))
    admin.create_topics([NewTopic(topic, 3, 1)])[topic].result(30)
    # NOTE: create 回來時 metadata 可能還沒傳播（#110），等到 3 個 partition 都有 leader 才送
    wait_until(lambda: _topic_ready(admin, topic, 3), f"topic {topic} metadata not ready", 30)
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
