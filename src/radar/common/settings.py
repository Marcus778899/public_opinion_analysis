from functools import lru_cache
from typing import Annotated

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy import URL


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

    host: str
    port: int = 5432
    db: str
    user: str
    password: SecretStr

    def url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.db,
        )


class KafkaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KAFKA_")

    bootstrap_servers: str
    client_id: str = "radar"


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="API_")

    # 允許跨網域呼叫的來源，逗號分隔；預設空白代表不開放任何跨網域請求
    cors_origins: Annotated[list[str], NoDecode] = []

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip().rstrip("/") for o in value.split(",") if o.strip()]
        return value


class SchedulerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCHEDULER_")

    api_url: str = "http://localhost:8000"
    sync_interval_sec: int = 30
    due_posts_interval_sec: int = 30
    # 每輪最多派發幾篇重爬，避免一次湧入大量任務
    due_posts_limit: int = 500
    # 重爬間隔的倍率；只在端到端測試調小，正式環境維持 1
    time_scale: float = 1.0


class CrawlerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CRAWLER_")

    # 只在端到端測試設定，把請求導向假 PTT 伺服器；資料中的網址仍是 www.ptt.cc
    ptt_base_url: str | None = None
    min_interval_s: float = 2.0
    jitter_s: float = 2.0


@lru_cache
def get_postgres_settings() -> PostgresSettings:
    return PostgresSettings()


@lru_cache
def get_kafka_settings() -> KafkaSettings:
    return KafkaSettings()
