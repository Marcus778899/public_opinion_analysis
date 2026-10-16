from functools import lru_cache
from pathlib import Path
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


class ConnectSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONNECT_")

    url: str = "http://localhost:8083"
    # Kafka Connect 啟動要載入 plugin，冷啟動常需 1 分鐘以上
    ready_timeout_s: float = 180.0


class InferenceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INFERENCE_")

    # models/<model_version>/；compose 內為 /app/models/<model_version>
    model_dir: Path
    # 文章 → 模型輸入文字 hash 的 LRU 上限（開發規格 7.18）
    cache_size: int = 200_000
    batch_size: int = 100


class CdcWatchdogSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CDC_WATCHDOG_")

    connector_name: str = "radar-cdc"
    slot_name: str = "radar_cdc"
    interval_s: float = 30.0
    restart_backoff_initial_s: float = 30.0
    restart_backoff_max_s: float = 600.0
    slot_inactive_alert_s: float = 300.0
    slot_lag_alert_bytes: int = 256 * 1024 * 1024
    # healthchecks.io 的 ping URL；None 時不送 heartbeat（測試與 e2e 不設）
    heartbeat_url: str | None = None
    # Connect、heartbeat、PG 查詢共用；卡住時 heartbeat 會停，外部服務才會發現
    request_timeout_s: float = 10.0

    @field_validator("heartbeat_url", mode="before")
    @classmethod
    def _blank_heartbeat_is_none(cls, value: object) -> object:
        # NOTE: e2e 以空字串覆寫 .env 的值來關閉 heartbeat（infra/docker-compose.e2e.yaml）
        if isinstance(value, str) and not value.strip():
            return None
        return value


class HeatSettings(BaseSettings):
    """熱度偵測（開發規格 7.20）；門檻預設值見 S5-04。"""

    model_config = SettingsConfigDict(env_prefix="HEAT_")

    # 回放與驗收時改成 replay.cdc.comments，並換 consumer_group，state 才不會和正式的混在一起
    input_topic: str = "cdc.public.comments"
    consumer_group: str = "heat"
    state_dir: Path = Path("state")
    window_min: int = 10
    grace_min: int = 2
    # 推文時間比觀測時間早超過這麼久的不計入（補抓、舊爆文；開發規格 7.20）
    max_delay_min: int = 30
    # 觀測時間比處理當下早超過這麼久的只更新基準、不觸發警示
    stale_after_min: int = 60
    ewma_alpha: float = 0.02
    # watermark 一次前進超過這麼多分鐘時，只補最後這幾分鐘的 0
    max_gap_min: int = 1440
    z_threshold: float = 3.0
    min_count: int = 30
    cooldown_min: int = 30
    warmup_min: int = 60
    min_std: float = 1.0


class SchemaRegistrySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCHEMA_REGISTRY_")

    # Apicurio 的 Confluent 相容 API；docker-compose 內為 http://apicurio:8080/apis/ccompat/v7
    url: str = "http://localhost:8080/apis/ccompat/v7"


class ClickHouseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLICKHOUSE_")

    url: str = "http://localhost:8123"
    db: str = "radar"
    user: str
    password: SecretStr


class GeminiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GEMINI_")

    api_key: SecretStr
    base_url: str = "https://generativelanguage.googleapis.com"
    # 額度以「專案 × 模型」計算；gemini-3.5-flash 免費只有 20 次/天，不適合批次標註
    model: str = "gemini-3.1-flash-lite"
    min_interval_s: float = 4.0


class GroqSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GROQ_")

    api_key: SecretStr
    base_url: str = "https://api.groq.com/openai/v1"
    model: str = "qwen/qwen3.8-27b"
    min_interval_s: float = 2.0


class OpenRouterSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENROUTER_")

    api_key: SecretStr
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "google/gemma-4-31b-it:free"
    min_interval_s: float = 4.0


class LabelingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LABEL_")

    # 內文超過此長度截斷，控制每篇的 token 數（開發規格 7.11）
    max_chars: int = 2000
    # 主要標註者的服務商；backfill 固定用它，不混用
    primary: str = "groq"
    # 串流標註的備援順序，主要標註者每日額度用完時依序改用
    fallbacks: Annotated[list[str], NoDecode] = ["gemini"]

    @field_validator("fallbacks", mode="before")
    @classmethod
    def _split_fallbacks(cls, value: object) -> object:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value


@lru_cache
def get_postgres_settings() -> PostgresSettings:
    return PostgresSettings()


@lru_cache
def get_kafka_settings() -> KafkaSettings:
    return KafkaSettings()
