from datetime import UTC, datetime

import pytest

from radar.bot.stats import (
    ClickHouseQueries,
    PostSentiment,
    PostStats,
    boards_literal,
    post_ids_literal,
)

PID = "Stock.M.1792000000.A.ABC"
PID2 = "Stock.M.1792000001.A.DEF"
NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)


class FakeClickHouse:
    def __init__(self, *results) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict | None]] = []

    def query_rows(self, sql, params=None):
        self.calls.append((sql, params))
        return self.results.pop(0) if self.results else []


def queries(ch: FakeClickHouse) -> ClickHouseQueries:
    return ClickHouseQueries(ch, hot_window_min=60, hot_limit=5)  # type: ignore[arg-type]


def test_post_ids_literal_quotes_each_id():
    assert post_ids_literal([PID, PID2]) == f"['{PID}','{PID2}']"


def test_post_ids_literal_rejects_injection():
    with pytest.raises(ValueError):
        post_ids_literal(["x'] OR 1=1 --"])


def test_post_stats_empty_list_does_not_query():
    ch = FakeClickHouse()

    assert queries(ch).post_stats([]) == {}
    assert ch.calls == []


def test_post_stats_maps_rows_and_missing_prediction():
    row = {"post_id": PID, "board": "Stock", "title": "t", "push": "3", "boo": "1", "arrow": "2"}
    predicted = {**row, "post_id": PID2, "polarity": "negative", "score": 0.7}
    ch = FakeClickHouse([{**row, "polarity": "", "score": 0}, predicted])

    result = queries(ch).post_stats([PID, PID2])

    assert result[PID] == PostStats(PID, "Stock", "t", 3, 1, 2, None)
    assert result[PID2].sentiment == PostSentiment("negative", 0.7)


def test_hot_passes_window_limit_and_board_filter():
    ch = FakeClickHouse()

    queries(ch).hot(["Stock"])

    _, params = ch.calls[0]
    assert params is not None
    assert (params["window_min"], params["limit"], params["boards"]) == ("60", "5", "['Stock']")


def test_hot_all_boards_passes_empty_filter():
    ch = FakeClickHouse()

    queries(ch).hot(None)

    _, params = ch.calls[0]
    assert params is not None and params["boards"] == "[]"


def test_boards_literal_quotes_each_board():
    assert boards_literal(["Stock", "Boy-Girl", "Tech_Job"]) == "['Stock','Boy-Girl','Tech_Job']"


@pytest.mark.parametrize("board", ["Stock'", "a b", ""])
def test_boards_literal_rejects_invalid_names(board):
    with pytest.raises(ValueError):
        boards_literal([board])


def test_overview_invalid_board_rejected_without_query():
    ch = FakeClickHouse()

    with pytest.raises(ValueError):
        queries(ch).overview("x' OR 1=1", NOW)

    assert ch.calls == []


def test_hot_post_missing_from_posts_latest_still_listed():
    ch = FakeClickHouse([{"post_id": PID, "recent": "4"}], [])

    [hot] = queries(ch).hot(None)

    assert (hot.stats.post_id, hot.stats.board, hot.stats.title, hot.recent) == (
        PID,
        "Stock",
        None,
        4,
    )
