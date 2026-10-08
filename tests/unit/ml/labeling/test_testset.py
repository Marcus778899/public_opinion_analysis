from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from radar.common.enums import Polarity
from radar.common.schemas import Sentiment
from radar.ml.labeling.testset import (
    HUMAN_LABELS_FILE,
    HumanLabel,
    append_human_label,
    load_human_labels,
    load_post_ids,
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


def test_select_testset_splits_size_across_boards():
    ch = FakeClickHouse(
        [row("g1", "Gossiping"), row("g2", "Gossiping")], [row("s1")], [row("t1", "Tech_Job")]
    )

    ids = select_testset(ch, 4, ["Gossiping", "Stock", "Tech_Job"])

    assert ids == ["g1", "g2", "s1", "t1"]
    assert [q[1]["limit"] for q in ch.queries] == ["2", "1", "1"]
