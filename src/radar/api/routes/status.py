from confluent_kafka import KafkaException
from fastapi import APIRouter

from radar.api.deps import AdminConsumer, Repository
from radar.api.kafka_ops import count_dlq_messages
from radar.api.schemas import StatusOut
from radar.common.log import log

router = APIRouter(tags=["status"])


@router.get("/status", response_model=StatusOut)
def get_status(repo: Repository, consumer: AdminConsumer) -> StatusOut:
    try:
        dlq_count = count_dlq_messages(consumer)
    except KafkaException as e:
        # Kafka 異常時仍回傳看板狀態，不讓整個 /status 失敗
        log.warning("dlq count unavailable: %s", e)
        dlq_count = -1
    return StatusOut(boards=repo.statuses(), dlq_count=dlq_count)
