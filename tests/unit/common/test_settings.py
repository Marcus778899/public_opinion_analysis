import pytest
from pydantic import ValidationError

from radar.common.settings import ApiSettings, KafkaSettings, PostgresSettings

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
