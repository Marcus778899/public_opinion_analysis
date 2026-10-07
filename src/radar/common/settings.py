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


@lru_cache
def get_postgres_settings() -> PostgresSettings:
    return PostgresSettings()


@lru_cache
def get_kafka_settings() -> KafkaSettings:
    return KafkaSettings()
