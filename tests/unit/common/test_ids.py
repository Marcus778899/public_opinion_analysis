import pytest

from radar.common.ids import make_post_id, split_post_id


def test_make_post_id_joins_board_and_filename():
    assert make_post_id("Stock", "M.1759730000.A.1B2") == "Stock.M.1759730000.A.1B2"


def test_make_post_id_accepts_underscore_board():
    assert make_post_id("Tech_Job", "M.1.A.abc") == "Tech_Job.M.1.A.abc"


@pytest.mark.parametrize("filename", ["", "M.123.A", "M.abc.A.1B2", "X.1.A.1B2", "M.1.A.1B2.html"])
def test_make_post_id_rejects_malformed_filename(filename):
    with pytest.raises(ValueError, match="filename"):
        make_post_id("Stock", filename)


@pytest.mark.parametrize("board", ["", "Sto ck", "Stock.x"])
def test_make_post_id_rejects_invalid_board(board):
    with pytest.raises(ValueError, match="board"):
        make_post_id(board, "M.1.A.1B2")


def test_split_post_id_is_inverse_of_make():
    assert split_post_id(make_post_id("Gossiping", "M.1.A.1B2")) == ("Gossiping", "M.1.A.1B2")


def test_split_post_id_keeps_dots_in_filename():
    assert split_post_id("Stock.M.1759730000.A.1B2")[1] == "M.1759730000.A.1B2"


def test_split_post_id_rejects_missing_separator():
    with pytest.raises(ValueError):
        split_post_id("Stock")
