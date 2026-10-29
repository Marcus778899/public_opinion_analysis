from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from radar.common.settings import PostgresSettings


def make_engine(
    settings: PostgresSettings, *, pool_size: int = 5, statement_timeout_sec: float | None = None
) -> Engine:
    kwargs: dict[str, object] = {"pool_size": pool_size, "pool_pre_ping": True}
    if statement_timeout_sec is not None:
        # NOTE: PG 的 statement_timeout 單位是毫秒，用連線選項讓每條連線都套用
        options = f"-c statement_timeout={round(statement_timeout_sec * 1000)}"
        kwargs["connect_args"] = {"options": options}
    return create_engine(settings.url(), **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    # NOTE: commit 後仍可讀取物件屬性，避免 API 回傳時觸發額外查詢
    return sessionmaker(engine, expire_on_commit=False)
