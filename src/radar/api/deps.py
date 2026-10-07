"""FastAPI 依賴注入；測試以 app.dependency_overrides 換成 fake。"""

from collections.abc import Iterator
from typing import Annotated

from confluent_kafka import Consumer
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from radar.api.repository import BoardRepository
from radar.common.kafka.producer import JsonProducer


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_repository(session: Annotated[Session, Depends(get_session)]) -> BoardRepository:
    return BoardRepository(session)


def get_producer(request: Request) -> JsonProducer:
    return request.app.state.producer


def get_admin_consumer(request: Request) -> Consumer:
    """只用來查 watermark，不 subscribe。"""
    return request.app.state.admin_consumer


Repository = Annotated[BoardRepository, Depends(get_repository)]
Producer = Annotated[JsonProducer, Depends(get_producer)]
AdminConsumer = Annotated[Consumer, Depends(get_admin_consumer)]
