import pytest
from pydantic import ValidationError

from radar.api.schemas import BoardCreate, BoardUpdate


def test_board_create_rejects_interval_below_30():
    with pytest.raises(ValidationError):
        BoardCreate(board="Stock", interval_sec=29)


@pytest.mark.parametrize("name", ["", "Sto ck", "Stock/../x", "股票"])
def test_board_create_rejects_invalid_board_name(name):
    with pytest.raises(ValidationError, match="board may only contain"):
        BoardCreate(board=name, interval_sec=60)


def test_board_create_defaults_enabled_and_recrawl_min_push():
    data = BoardCreate(board="Tech_Job", interval_sec=600)

    assert (data.enabled, data.recrawl_min_push) == (True, 0)


@pytest.mark.parametrize("payload", [{}, {"enabled": None}])
def test_board_update_requires_at_least_one_field(payload):
    with pytest.raises(ValidationError, match="at least one field"):
        BoardUpdate(**payload)


def test_board_update_changes_only_includes_given_fields():
    assert BoardUpdate(enabled=False).changes() == {"enabled": False}


def test_board_update_rejects_negative_recrawl_min_push():
    with pytest.raises(ValidationError):
        BoardUpdate(recrawl_min_push=-1)
