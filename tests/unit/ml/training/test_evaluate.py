import pytest

from radar.common.enums import Polarity
from radar.ml.training.dataset import Example
from radar.ml.training.evaluate import (
    agreements_by_board,
    evaluate_by_board,
    evaluate_model,
    llm_vs_human,
    render_markdown,
)
from radar.ml.training.train import train

POS, NEU, NEG = Polarity.POSITIVE, Polarity.NEUTRAL, Polarity.NEGATIVE


def test_evaluate_model_macro_f1_and_confusion(examples):
    pipeline = train(examples, seed=42)

    report = evaluate_model(pipeline, examples)

    assert report.n == 36
    assert report.macro_f1 == pytest.approx(1.0)
    assert report.confusion[NEG] == {POS: 0, NEG: 12, NEU: 0}


def test_evaluate_model_empty_raises(examples):
    with pytest.raises(ValueError, match="empty"):
        evaluate_model(train(examples, seed=42), [])


def test_llm_vs_human_only_overlap():
    agreement = llm_vs_human(
        "groq:q", {"a": NEG, "b": POS, "c": NEU}, {"a": NEG, "b": NEU, "x": POS}
    )

    assert (agreement.labeler, agreement.n, agreement.accuracy) == ("groq:q", 2, 0.5)


def test_llm_vs_human_no_overlap():
    agreement = llm_vs_human("x", {"a": NEG}, {"b": NEG})

    assert (agreement.n, agreement.accuracy, agreement.cohen_kappa) == (0, 0.0, 0.0)


def test_render_markdown_lists_agreements(examples):
    report = evaluate_model(train(examples, seed=42), examples)
    agreements = [llm_vs_human("groq:q", {"a": NEG}, {"a": NEG})]

    md = render_markdown("tfidf-lr-1", report, agreements, board_reports={}, board_agreements={})

    assert "| 整體 | 36 | **1.000** |" in md
    assert "| negative | 0 | 12 | 0 |" in md
    assert "| `groq:q` | 整體 | 1 | 100.0% |" in md


def on_board(examples: list[Example], board: str) -> list[Example]:
    return [Example(e.post_id.replace("Stock", board), board, e.text, e.polarity) for e in examples]


def two_boards(examples: list[Example]) -> list[Example]:
    """Tech_Job 只取每類 2 篇，Stock 保留全部 36 篇。"""
    small = [e for i, e in enumerate(examples) if i % 12 < 2]
    return on_board(small, "Tech_Job") + examples


def test_evaluate_by_board_groups_examples_per_board(examples):
    pipeline = train(examples, seed=42)

    reports = evaluate_by_board(pipeline, two_boards(examples))

    assert {b: r.n for b, r in reports.items()} == {"Stock": 36, "Tech_Job": 6}


def test_evaluate_by_board_sorted_by_board_name(examples):
    pipeline = train(examples, seed=42)
    mixed = on_board(examples[:3], "Tech_Job") + on_board(examples[:3], "Gossiping")

    assert list(evaluate_by_board(pipeline, mixed)) == ["Gossiping", "Tech_Job"]


def test_agreements_by_board_uses_post_board_for_each_labeler():
    human = {"g1": NEG, "g2": POS, "s1": NEU, "unknown": NEG}
    boards = {"g1": "Gossiping", "g2": "Gossiping", "s1": "Stock"}
    llm = {"groq:q": {"g1": NEG, "g2": NEG, "s1": NEU}, "claude": {"g1": NEG}}

    result = agreements_by_board(llm, human, boards)

    assert list(result) == ["Gossiping", "Stock"]
    assert [(a.labeler, a.n, a.accuracy) for a in result["Gossiping"]] == [
        ("groq:q", 2, 0.5),
        ("claude", 1, 1.0),
    ]
    assert [(a.labeler, a.n) for a in result["Stock"]] == [("groq:q", 1), ("claude", 0)]


def render_with_boards(examples):
    pipeline = train(examples, seed=42)
    mixed = two_boards(examples)
    human = {e.post_id: e.polarity for e in mixed}
    boards = {e.post_id: e.board for e in mixed}
    llm = {"groq:q": dict(human)}
    return render_markdown(
        "tfidf-lr-1",
        evaluate_model(pipeline, mixed),
        [llm_vs_human("groq:q", llm["groq:q"], human)],
        board_reports=evaluate_by_board(pipeline, mixed),
        board_agreements=agreements_by_board(llm, human, boards),
    )


def test_render_markdown_has_overall_and_per_board_f1_tables(examples):
    md = render_with_boards(examples)

    assert "| 範圍 | 篇數 | macro-F1 | positive F1 | negative F1 | neutral F1 |" in md
    assert "| 整體 | 42 | **1.000** | 1.000 | 1.000 | 1.000 |" in md
    assert "| Stock（樣本少，只供參考） | 36 |" in md


def test_render_markdown_has_per_board_agreements(examples):
    md = render_with_boards(examples)

    assert "| `groq:q` | 整體 | 42 | 100.0% |" in md
    assert "| `groq:q` | Stock（樣本少，只供參考） | 36 | 100.0% |" in md


def test_render_markdown_marks_small_board_as_reference_only(examples):
    pipeline = train(examples, seed=42)
    big = [
        Example(f"{e.post_id}.{i}", "Gossiping", e.text, e.polarity)
        for i in range(2)
        for e in examples
    ]
    report = evaluate_model(pipeline, big)

    md = render_markdown(
        "v",
        report,
        [],
        board_reports=evaluate_by_board(pipeline, big + on_board(examples[:3], "Tech_Job")),
        board_agreements={},
    )

    assert "| Gossiping | 72 |" in md
    assert "| Tech_Job（樣本少，只供參考） | 3 |" in md
