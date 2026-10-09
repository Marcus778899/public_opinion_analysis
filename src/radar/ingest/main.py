"""Ingest consumer：消費 raw.posts，批次寫入 PG（設計文件 5）。"""

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from radar.common.db.session import make_engine, make_session_factory
from radar.common.kafka import names
from radar.common.kafka.consumer import BatchConsumer, Rejection, TransientError
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.log import log, setup_logging
from radar.common.schemas import RawPost
from radar.common.settings import get_kafka_settings, get_postgres_settings
from radar.ingest.writer import DATA_ERRORS, write_batch, write_each


class IngestHandler:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __call__(self, posts: list[RawPost]) -> list[Rejection]:
        """資料錯誤改逐筆寫入、回報 Rejection；其他 DB 錯誤直接拋出讓服務停下。"""
        rejections: list[Rejection] = []
        try:
            with self._session_factory() as session:
                try:
                    stats = write_batch(session, posts)
                except DATA_ERRORS as e:
                    log.warning("batch write failed, retrying one by one: %s", e)
                    session.rollback()
                    stats, rejections = write_each(session, posts)
                session.commit()
        except OperationalError as e:
            raise TransientError(f"database unavailable: {e}") from e
        log.info(
            "batch received=%d posts_written=%d comments_written=%d comments_deleted=%d "
            "marked_deleted=%d",
            stats.received,
            stats.posts_written,
            stats.comments_written,
            stats.comments_deleted,
            stats.marked_deleted,
        )
        return rejections


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("ingest")
    kafka = get_kafka_settings()
    engine = make_engine(get_postgres_settings())
    producer = JsonProducer(kafka)
    consumer = BatchConsumer(
        kafka,
        group_id="ingest",
        topics=[names.RAW_POSTS],
        model=RawPost,
        handler=IngestHandler(make_session_factory(engine)),
        dlq=DlqPublisher(producer, "ingest"),
        batch_size=500,
        batch_timeout_s=1.0,
    )
    try:
        consumer.run()
    finally:
        producer.flush()
        engine.dispose()


if __name__ == "__main__":
    main()
