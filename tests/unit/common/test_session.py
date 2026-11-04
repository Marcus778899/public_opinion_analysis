from radar.common.db import session as session_module
from radar.common.settings import PostgresSettings


def test_make_engine_timeout_rounds_fractional_seconds_to_ms(monkeypatch):
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        session_module, "create_engine", lambda url, **kw: seen.update(kw) or object()
    )

    session_module.make_engine(
        PostgresSettings(host="h", db="d", user="u", password="p"), statement_timeout_sec=0.5
    )

    assert seen["connect_args"] == {"options": "-c statement_timeout=500"}
