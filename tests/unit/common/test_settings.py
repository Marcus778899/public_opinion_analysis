import pytest
from pydantic import ValidationError

from radar.common.settings import (
    ApiSettings,
    ClickHouseSettings,
    ConnectSettings,
    CrawlerSettings,
    KafkaSettings,
    LabelingSettings,
    PostgresSettings,
    SchedulerSettings,
)

PG_ENV = {
    "POSTGRES_HOST": "db",
    "POSTGRES_PORT": "6543",
    "POSTGRES_DB": "radar",
    "POSTGRES_USER": "radar",
    "POSTGRES_PASSWORD": "p@ss%word",
}


@pytest.fixture
def pg_env(monkeypatch):
    for k, v in PG_ENV.items():
        monkeypatch.setenv(k, v)


def test_postgres_settings_reads_prefixed_env(pg_env):
    s = PostgresSettings()

    assert (s.host, s.port, s.db, s.user) == ("db", 6543, "radar", "radar")
    assert s.password.get_secret_value() == "p@ss%word"


def test_postgres_settings_missing_required_env_raises(monkeypatch):
    for k in PG_ENV:
        monkeypatch.delenv(k, raising=False)

    with pytest.raises(ValidationError):
        PostgresSettings()


def test_postgres_url_uses_psycopg_driver_and_keeps_password(pg_env):
    url = PostgresSettings().url()

    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss%word"
    assert (url.host, url.port, url.database) == ("db", 6543, "radar")


def test_postgres_password_hidden_in_repr(pg_env):
    assert "p@ss%word" not in repr(PostgresSettings())


def test_kafka_settings_default_client_id(monkeypatch):
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "a:9092,b:9094")

    s = KafkaSettings()

    assert s.bootstrap_servers == "a:9092,b:9094"
    assert s.client_id == "radar"


def test_api_settings_cors_origins_default_empty(monkeypatch):
    monkeypatch.delenv("API_CORS_ORIGINS", raising=False)

    assert ApiSettings().cors_origins == []


def test_api_settings_cors_origins_split_by_comma(monkeypatch):
    monkeypatch.setenv("API_CORS_ORIGINS", " https://a.example.com/ , http://localhost:3000,, ")

    assert ApiSettings().cors_origins == ["https://a.example.com", "http://localhost:3000"]


def test_api_settings_cors_origins_empty_string(monkeypatch):
    monkeypatch.setenv("API_CORS_ORIGINS", "")

    assert ApiSettings().cors_origins == []


def test_scheduler_and_crawler_settings_defaults(monkeypatch):
    for key in ("SCHEDULER_API_URL", "SCHEDULER_TIME_SCALE", "CRAWLER_PTT_BASE_URL"):
        monkeypatch.delenv(key, raising=False)

    scheduler, crawler = SchedulerSettings(), CrawlerSettings()

    assert (scheduler.api_url, scheduler.time_scale, scheduler.due_posts_limit) == (
        "http://localhost:8000",
        1.0,
        500,
    )
    assert (crawler.ptt_base_url, crawler.min_interval_s, crawler.jitter_s) == (None, 2.0, 2.0)


def test_scheduler_settings_from_env(monkeypatch):
    monkeypatch.setenv("SCHEDULER_TIME_SCALE", "0.05")
    monkeypatch.setenv("SCHEDULER_API_URL", "http://api:8000")

    settings = SchedulerSettings()

    assert (settings.time_scale, settings.api_url) == (0.05, "http://api:8000")


def test_connect_settings_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("CONNECT_URL", raising=False)

    assert ConnectSettings().url == "http://localhost:8083"


def test_clickhouse_settings_reads_prefixed_env(monkeypatch):
    for k, v in {
        "CLICKHOUSE_URL": "http://ch:8123",
        "CLICKHOUSE_DB": "radar",
        "CLICKHOUSE_USER": "radar",
        "CLICKHOUSE_PASSWORD": "secret",
    }.items():
        monkeypatch.setenv(k, v)

    s = ClickHouseSettings()

    assert (s.url, s.db, s.user, s.password.get_secret_value()) == (
        "http://ch:8123",
        "radar",
        "radar",
        "secret",
    )


def test_clickhouse_settings_missing_password_raises(monkeypatch):
    monkeypatch.setenv("CLICKHOUSE_USER", "radar")
    monkeypatch.delenv("CLICKHOUSE_PASSWORD", raising=False)

    with pytest.raises(ValidationError):
        ClickHouseSettings()


def test_labeling_settings_fallbacks_split_from_env(monkeypatch):
    monkeypatch.setenv("LABEL_FALLBACKS", "gemini, openrouter")

    assert LabelingSettings().fallbacks == ["gemini", "openrouter"]


def test_labeling_settings_defaults(monkeypatch):
    for var in ("LABEL_PRIMARY", "LABEL_FALLBACKS", "LABEL_MAX_CHARS"):
        monkeypatch.delenv(var, raising=False)

    s = LabelingSettings()

    assert (s.primary, s.fallbacks, s.max_chars) == ("groq", ["gemini"], 2000)
