"""管理 API（設計文件 4.3）。啟動：uvicorn radar.api.main:app"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from confluent_kafka import Consumer
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask

from radar.api.routes import boards, status
from radar.common.db.session import make_engine, make_session_factory
from radar.common.kafka.config import consumer_config
from radar.common.kafka.producer import JsonProducer, ProducerFatalError
from radar.common.log import log, setup_logging
from radar.common.settings import ApiSettings, get_kafka_settings, get_postgres_settings

ADMIN_GROUP_ID = "radar-api-admin"
RESTART_EXIT_CODE = 70  # EX_SOFTWARE；非 0 讓 docker 的 restart policy 重啟


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging("api")
    engine = make_engine(get_postgres_settings())
    kafka = get_kafka_settings()
    app.state.session_factory = make_session_factory(engine)
    app.state.producer = JsonProducer(kafka)
    app.state.admin_consumer = Consumer(consumer_config(kafka, ADMIN_GROUP_ID))
    log.info("api started")
    try:
        yield
    finally:
        try:
            app.state.producer.flush()
        except Exception as e:  # 關閉流程不能因 Kafka 失敗而中斷
            log.warning("producer flush on shutdown failed: %s", e)
        app.state.admin_consumer.close()
        engine.dispose()
        log.info("api stopped")


def exit_for_restart() -> None:
    """先把 log（含 Slack 佇列）送完再結束；用 os._exit 是因為 uvicorn 收到 SIGTERM 會以 0 結束。"""
    log.close()
    os._exit(RESTART_EXIT_CODE)


async def handle_producer_fatal(request: Request, exc: ProducerFatalError) -> JSONResponse:
    log.critical(
        "producer fatal on %s %s, exiting for restart: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        {"detail": "kafka unavailable"},
        status_code=503,
        background=BackgroundTask(exit_for_restart),
    )


def create_app(*, settings: ApiSettings | None = None, use_lifespan: bool = True) -> FastAPI:
    """use_lifespan=False 給測試用，不連真的 PG / Kafka，依賴由 dependency_overrides 提供。"""
    settings = settings or ApiSettings()
    app = FastAPI(title="Radar API", lifespan=lifespan if use_lifespan else None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
        # 目前沒有登入機制，不需要帶 cookie；開啟時 allow_origins 不可用 "*"
        allow_credentials=False,
    )
    app.add_exception_handler(ProducerFatalError, handle_producer_fatal)  # type: ignore[arg-type]
    app.include_router(boards.router)
    app.include_router(status.router)
    return app


app = create_app()
