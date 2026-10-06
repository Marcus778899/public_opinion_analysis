from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from radar.common.settings import PostgresSettings


def make_engine(settings: PostgresSettings, *, pool_size: int = 5) -> Engine:
    return create_engine(settings.url(), pool_size=pool_size, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    # NOTE: commit 後仍可讀取物件屬性，避免 API 回傳時觸發額外查詢
    return sessionmaker(engine, expire_on_commit=False)
