from datetime import UTC, datetime

import pytest

from radar.common.enums import Polarity
from radar.common.schemas import Label, Sentiment
from radar.ml.labeling.backfill import parse_args, run_backfill, select_testset_posts
from radar.ml.labeling.llm import LabelerError, QuotaExhaustedError, RetryableLabelerError
from tests.unit.ml.fakes import FakeClickHouse, ScriptedLabeler, post, row

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
WHOLE = [Sentiment(target=None, polarity=Polarity.NEUTRAL)]


def run(labeler, posts, **kwargs):
    published: list[Label] = []
    sleeps: list[float] = []
    result = run_backfill(
        posts,
        labeler,
        "prompt-v4",
        published.append,
        now=lambda: NOW,
        sleep=sleeps.append,
        **kwargs,
    )
    return result, published, sleeps


def test_run_backfill_publishes_label_per_post():
    posts = [post("Stock.M.1759730000.A.1B2"), post("Stock.M.1759730001.A.1B3")]

    result, published, _ = run(ScriptedLabeler(WHOLE, WHOLE, name="groq:q"), posts)

    assert (result.labeled, result.skipped, result.stopped_by_quota) == (2, 0, False)
    assert [(p.post_id, p.labeler, p.version, p.labeled_at) for p in published] == [
        ("Stock.M.1759730000.A.1B2", "groq:q", "prompt-v4", NOW),
        ("Stock.M.1759730001.A.1B3", "groq:q", "prompt-v4", NOW),
    ]


def test_run_backfill_retries_retryable_then_succeeds():
    labeler = ScriptedLabeler(RetryableLabelerError("429"), RetryableLabelerError("503"), WHOLE)

    result, published, sleeps = run(labeler, [post()])

    assert result.labeled == 1 and len(published) == 1
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0]


def test_run_backfill_retryable_exhausted_counts_skipped():
    labeler = ScriptedLabeler(*[RetryableLabelerError("x")] * 3, WHOLE)

    result, published, _ = run(labeler, [post(), post("Stock.M.1759730001.A.1B3")], max_retries=2)

    assert (result.labeled, result.skipped) == (1, 1)
    assert published[0].post_id == "Stock.M.1759730001.A.1B3"


def test_run_backfill_labeler_error_skips_post():
    labeler = ScriptedLabeler(LabelerError("blocked"), WHOLE)

    result, _, sleeps = run(labeler, [post(), post("Stock.M.1759730001.A.1B3")])

    assert (result.labeled, result.skipped) == (1, 1)
    assert sleeps == []


def test_run_backfill_quota_exhausted_stops_early():
    labeler = ScriptedLabeler(WHOLE, QuotaExhaustedError("daily"))
    posts = [post(), post("Stock.M.1759730001.A.1B3"), post("Stock.M.1759730002.A.1B4")]

    result, published, _ = run(labeler, posts)

    assert (result.labeled, result.stopped_by_quota) == (1, True)
    assert len(labeler.calls) == 2


def test_parse_args_defaults_and_choices():
    args = parse_args(["--per-board", "100"])

    assert (args.per_board, args.labeler, args.boards, args.dry_run) == (100, None, None, False)
    args = parse_args(["--per-board", "5", "--labeler", "gemini", "--boards", "Stock", "--dry-run"])
    assert (args.labeler, args.boards, args.dry_run) == ("gemini", ["Stock"], True)


def test_parse_args_requires_per_board():
    with pytest.raises(SystemExit):
        parse_args([])


def test_parse_args_requires_per_board_or_testset():
    assert parse_args(["--testset"]).testset is True
    assert parse_args(["--per-board", "5"]).testset is False


def test_parse_args_rejects_per_board_with_testset():
    with pytest.raises(SystemExit):
        parse_args(["--per-board", "5", "--testset"])


def clickhouse_for_testset(labeled: list[str], found: list[str]) -> FakeClickHouse:
    """依序回傳：已標過的 post_id、fetch_posts 找到的文章。"""
    return FakeClickHouse([{"post_id": p} for p in labeled], [row(p) for p in found])


def test_select_testset_posts_skips_already_labeled():
    ch = clickhouse_for_testset(labeled=["a"], found=["b", "c"])

    posts = select_testset_posts(ch, ["a", "b", "c"], "groq:q", "prompt-v4")

    assert [p.post_id for p in posts] == ["b", "c"]
    assert ch.queries[1][1]["ids"] == "['b','c']"  # 已標過的不再取內容


def test_select_testset_posts_keeps_testset_order():
    ch = clickhouse_for_testset(labeled=[], found=["c", "a", "b"])

    posts = select_testset_posts(ch, ["b", "c", "a"], "groq:q", "prompt-v4")

    assert [p.post_id for p in posts] == ["b", "c", "a"]


def test_select_testset_posts_missing_in_clickhouse_is_skipped():
    ch = clickhouse_for_testset(labeled=[], found=["a"])

    posts = select_testset_posts(ch, ["a", "gone"], "groq:q", "prompt-v4")

    assert [p.post_id for p in posts] == ["a"]
