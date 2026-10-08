import json
from datetime import UTC, datetime

import pytest

from radar.common.schemas import Label
from radar.ml.labeling.manual import (
    MANUAL_LABELER,
    BatchPost,
    batch_path_for,
    export_batch,
    export_testset_batch,
    export_testset_query,
    import_outputs,
    read_batch,
)
from radar.ml.labeling.prompt import PROMPT_VERSION
from tests.unit.ml.fakes import FakeClickHouse, row

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
BATCH = [BatchPost(post_id="a", board="Stock", title="t", content="c"),
         BatchPost(post_id="b", board="Stock", title="t", content="c")]  # fmt: skip


def output_line(post_id: str, polarity: str = "neutral", **extra) -> str:
    return json.dumps(
        {"post_id": post_id, "sentiments": [{"target": None, "polarity": polarity}], **extra}
    )


def test_export_batch_writes_truncated_posts_and_excludes_testset(tmp_path):
    long_row = {**row("a"), "content": "一二三四五六"}
    ch = FakeClickHouse([long_row, row("t1"), row("b")])

    path = export_batch(ch, "groq:q", 2, {"t1"}, 3, tmp_path, NOW)

    batch = read_batch(path)
    assert path.name == "batch-20261007T120000.jsonl"
    assert [p.post_id for p in batch] == ["a", "b"]
    assert batch[0].content == "一二三"
    sql, params = ch.queries[0]
    assert "{primary:String}" in sql and "groq:q" not in sql
    assert params == {
        "primary": "groq:q",
        "manual": MANUAL_LABELER,
        "version": PROMPT_VERSION,
        "limit": "3",
    }


def test_export_batch_nothing_to_label_returns_none(tmp_path):
    assert export_batch(FakeClickHouse([]), "groq:q", 5, set(), 100, tmp_path, NOW) is None
    assert not any(tmp_path.iterdir())


def test_import_outputs_publishes_manual_labels(tmp_path):
    out = tmp_path / "batch-x.out.jsonl"
    out.write_text(output_line("a", "negative") + "\n\n" + output_line("b") + "\n")
    published: list[Label] = []

    count, errors = import_outputs(out, BATCH, published.append, lambda: NOW)

    assert (count, errors) == (2, [])
    assert {(p.post_id, p.labeler, p.version) for p in published} == {
        ("a", MANUAL_LABELER, PROMPT_VERSION),
        ("b", MANUAL_LABELER, PROMPT_VERSION),
    }


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        ([output_line("zzz")], "not in the batch"),
        ([output_line("a"), output_line("a")], "appears twice"),
        (
            ['{"post_id": "a", "sentiments": [{"target": "x", "polarity": "neutral"}]}'],
            "whole-post",
        ),
        (["not json"], "line 1"),
    ],
)
def test_import_outputs_any_error_publishes_nothing(tmp_path, lines, message):
    out = tmp_path / "batch-x.out.jsonl"
    out.write_text("\n".join([output_line("b"), *lines]) + "\n")
    published: list[Label] = []

    count, errors = import_outputs(out, BATCH, published.append, lambda: NOW)

    assert count == 0 and published == []
    assert any(message in e for e in errors)


def test_batch_path_for_output_name(tmp_path):
    assert batch_path_for(tmp_path / "batch-1.out.jsonl") == tmp_path / "batch-1.jsonl"


def test_batch_path_for_wrong_name_raises(tmp_path):
    with pytest.raises(ValueError, match="out.jsonl"):
        batch_path_for(tmp_path / "batch-1.jsonl")


def test_export_testset_query_filters_manual_labeler_version_and_ids():
    sql = export_testset_query()

    assert "post_id IN {ids:Array(String)}" in sql
    assert "labeler = {manual:String} AND version = {version:String}" in sql
    assert "{primary:String}" not in sql  # 不要求主要標註者先標


def test_export_testset_batch_writes_unlabeled_testset_posts_truncated(tmp_path):
    ch = FakeClickHouse([{**row("a"), "content": "一二三四五六"}, row("b")])

    path = export_testset_batch(ch, ["a", "b", "c"], 10, 3, tmp_path, NOW)

    assert path == tmp_path / "batch-20261007T120000.jsonl"
    assert [(p.post_id, p.content) for p in read_batch(path)] == [("a", "一二三"), ("b", "c")]
    assert ch.queries[0][1] == {
        "ids": "['a','b','c']",
        "manual": MANUAL_LABELER,
        "version": PROMPT_VERSION,
        "limit": "10",
    }


def test_export_testset_batch_nothing_left_returns_none(tmp_path):
    assert export_testset_batch(FakeClickHouse([]), ["a"], 10, 3, tmp_path, NOW) is None
    assert export_testset_batch(FakeClickHouse(), [], 10, 3, tmp_path, NOW) is None
