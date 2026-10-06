from typing import Any

from radar.common.settings import KafkaSettings

# NOTE: raw.html 單則上限 5MB（topics.yaml），producer 端也要放寬，否則在 client 就被擋下
MAX_MESSAGE_BYTES = 5 * 1024 * 1024


def producer_config(settings: KafkaSettings) -> dict[str, Any]:
    """開發規格 2.2：acks=all、idempotence、zstd。"""
    return {
        "bootstrap.servers": settings.bootstrap_servers,
        "client.id": settings.client_id,
        "acks": "all",
        "enable.idempotence": True,
        "compression.type": "zstd",
        "message.max.bytes": MAX_MESSAGE_BYTES,
    }


def consumer_config(settings: KafkaSettings, group_id: str) -> dict[str, Any]:
    """關閉 auto commit，由 BatchConsumer 處理完才手動 commit。"""
    return {
        "bootstrap.servers": settings.bootstrap_servers,
        "client.id": settings.client_id,
        "group.id": group_id,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    }


def admin_config(settings: KafkaSettings) -> dict[str, Any]:
    return {"bootstrap.servers": settings.bootstrap_servers, "client.id": settings.client_id}
