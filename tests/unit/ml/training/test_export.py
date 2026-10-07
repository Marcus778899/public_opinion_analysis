from datetime import UTC, datetime

from radar.common.enums import Polarity
from radar.ml.training.export import build_examples, dataset_name, fetch_rows
from tests.unit.ml.fakes import FakeClickHouse


def label_row(post_id: str, polarity: str = "negative") -> dict:
    return {
        "post_id": post_id,
        "board": "Stock",
        "title": "標題",
        "content": "內文很長",
        "polarity": polarity,
    }


def test_build_examples_excludes_testset():
    examples, stats = build_examples([label_row("a"), label_row("t")], {}, {"t"}, 100)

    assert [e.post_id for e in examples] == ["a"]
    assert stats.excluded_testset == 1


def test_build_examples_drops_secondary_disagreements():
    rows = [label_row("a", "negative"), label_row("b", "negative")]
    secondary = {"a": Polarity.NEGATIVE, "b": Polarity.NEUTRAL}

    examples, stats = build_examples(rows, secondary, set(), 100)

    assert [e.post_id for e in examples] == ["a"]
    assert stats.dropped_disagreements == 1


def test_build_examples_keeps_posts_without_secondary_label_and_truncates():
    examples, _ = build_examples([label_row("a", "positive")], {}, set(), 2)

    assert examples[0].polarity is Polarity.POSITIVE
    assert examples[0].text == "標題\n內文"


def test_fetch_rows_uses_params():
    ch = FakeClickHouse([label_row("a")])

    assert fetch_rows(ch, "groq:q", "prompt-v4") == [label_row("a")]
    assert ch.queries[0][1] == {"labeler": "groq:q", "version": "prompt-v4"}
    assert "NOT is_deleted" in ch.queries[0][0]


def test_dataset_name_is_filesystem_safe():
    now = datetime(2026, 10, 7, 12, 30, tzinfo=UTC)

    assert dataset_name("groq:qwen/qwen3.8-27b", "prompt-v4", now) == (
        "groq-qwen-qwen3.8-27b-prompt-v4-202610071230"
    )
