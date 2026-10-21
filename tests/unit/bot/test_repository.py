import uuid
from datetime import UTC, datetime

import pytest

from radar.bot import repository
from radar.bot.repository import filter_recipients
from radar.common.schemas import Alert

NOW = datetime(2026, 10, 17, 3, 0, tzinfo=UTC)


def make_alert(unit_type="post") -> Alert:
    return Alert(
        alert_id=uuid.UUID(int=1),
        unit_type=unit_type,
        unit_key="Stock.M.1.A.X" if unit_type == "post" else "Stock",
        board="Stock",
        window_start=NOW,
        window_end=NOW,
        value=45,
        baseline=3.2,
        zscore=8.0,
        sample_post_ids=[],
        created_at=NOW,
    )


@pytest.fixture
def infos(monkeypatch):
    lines: list[str] = []
    monkeypatch.setattr(repository.log, "info", lambda msg, *a, **k: lines.append(msg % a))
    return lines


def test_filter_recipients_disabled_setting_is_skipped_and_logged(infos):
    kept = filter_recipients(make_alert(), [(1, True, False), (2, False, False)])

    assert kept == [1]
    assert len(infos) == 1
    assert "chat 2" in infos[0] and "post Stock.M.1.A.X" in infos[0]
    assert "chat_settings disabled" in infos[0]


def test_filter_recipients_muted_post_is_skipped_and_logged(infos):
    kept = filter_recipients(make_alert(), [(3, None, True)])

    assert kept == []
    assert "chat 3" in infos[0] and "post muted" in infos[0]


def test_filter_recipients_none_skipped_logs_nothing(infos):
    kept = filter_recipients(make_alert("board"), [(1, None, False), (2, True, False)])

    assert kept == [1, 2]
    assert infos == []


def test_filter_recipients_empty_rows_returns_empty(infos):
    assert filter_recipients(make_alert(), []) == []
    assert infos == []
