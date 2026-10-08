from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from radar.common.enums import Polarity
from radar.common.schemas import Sentiment
from radar.ml.labeling.testset import (
    HUMAN_LABELS_FILE,
    TESTSET_SEED,
    HumanLabel,
    InsufficientPostsError,
    append_human_label,
    load_human_labels,
    load_post_ids,
    parse_board_counts,
    select_testset,
    write_post_ids,
)
from tests.unit.ml.fakes import FakeClickHouse, row

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def human(post_id: str, polarity: Polarity, note: str | None = None) -> HumanLabel:
    return HumanLabel(
        post_id=post_id,
        sentiments=[Sentiment(target=None, polarity=polarity)],
        labeled_at=NOW,
        note=note,
    )


def test_write_and_load_post_ids(tmp_path):
    write_post_ids(tmp_path, ["a", "b"])

    assert load_post_ids(tmp_path) == ["a", "b"]


def test_write_post_ids_refuses_overwrite(tmp_path):
    write_post_ids(tmp_path, ["a"])

    with pytest.raises(FileExistsError):
        write_post_ids(tmp_path, ["b"])
    assert load_post_ids(tmp_path) == ["a"]


def test_load_post_ids_missing_file_returns_empty(tmp_path):
    assert load_post_ids(tmp_path / "nope") == []


def test_append_and_load_human_labels_roundtrip(tmp_path):
    append_human_label(tmp_path, human("a", Polarity.NEGATIVE, note="反串"))

    loaded = load_human_labels(tmp_path)

    assert loaded["a"] == human("a", Polarity.NEGATIVE, note="反串")
    assert "反串" in (tmp_path / HUMAN_LABELS_FILE).read_text()


def test_load_human_labels_last_entry_wins(tmp_path):
    append_human_label(tmp_path, human("a", Polarity.NEGATIVE))
    append_human_label(tmp_path, human("a", Polarity.NEUTRAL))

    assert load_human_labels(tmp_path)["a"].sentiments[0].polarity is Polarity.NEUTRAL


def test_human_label_requires_whole_post_sentiment():
    with pytest.raises(ValidationError, match="whole-post"):
        HumanLabel(
            post_id="a",
            sentiments=[Sentiment(target="x", polarity=Polarity.NEUTRAL)],
            labeled_at=NOW,
        )


def test_select_testset_uses_each_board_quota_in_order():
    ch = FakeClickHouse(
        [row("g1", "Gossiping"), row("g2", "Gossiping")], [row("s1")], [row("t1", "Tech_Job")]
    )

    ids = select_testset(ch, {"Gossiping": 2, "Stock": 1, "Tech_Job": 1})

    assert ids == ["g1", "g2", "s1", "t1"]


def test_select_testset_queries_each_board_with_its_own_limit():
    ch = FakeClickHouse([row("g1", "Gossiping"), row("g2", "Gossiping")], [row("s1")])

    select_testset(ch, {"Gossiping": 2, "Stock": 1})

    assert [(q[1]["boards"], q[1]["limit"]) for q in ch.queries] == [
        ("['Gossiping']", "2"),
        ("['Stock']", "1"),
    ]


def test_select_testset_board_short_of_quota_raises_with_counts():
    ch = FakeClickHouse([row("g1", "Gossiping")], [row("t1", "Tech_Job")])

    with pytest.raises(InsufficientPostsError, match="Tech_Job: only 1 usable posts, need 30"):
        select_testset(ch, {"Gossiping": 1, "Tech_Job": 30})


def test_select_testset_uses_fixed_testset_seed():
    ch = FakeClickHouse([row("s1")])

    select_testset(ch, {"Stock": 1})

    assert ch.queries[0][1]["seed"] == str(TESTSET_SEED)


def test_parse_board_counts_valid_pairs_keep_order():
    counts = parse_board_counts(["Stock=90", "Gossiping=180", "Tech_Job=30"])

    assert list(counts.items()) == [("Stock", 90), ("Gossiping", 180), ("Tech_Job", 30)]


def test_parse_board_counts_missing_equals_raises():
    with pytest.raises(ValueError, match="<board>=<count>"):
        parse_board_counts(["Stock"])


@pytest.mark.parametrize("value", ["Stock=abc", "Stock=", "Stock=0", "Stock=-5"])
def test_parse_board_counts_non_integer_or_zero_raises(value):
    with pytest.raises(ValueError, match="count must be"):
        parse_board_counts([value])


@pytest.mark.parametrize("value", ["=10", "Sto ck=10", "股票=10"])
def test_parse_board_counts_invalid_board_name_raises(value):
    with pytest.raises(ValueError, match="invalid board"):
        parse_board_counts([value])


def test_parse_board_counts_duplicate_board_raises():
    with pytest.raises(ValueError, match="duplicate board"):
        parse_board_counts(["Stock=1", "Stock=2"])
