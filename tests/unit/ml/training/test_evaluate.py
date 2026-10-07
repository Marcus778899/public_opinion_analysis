import pytest

from radar.common.enums import Polarity
from radar.ml.training.evaluate import evaluate_model, llm_vs_human, render_markdown
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

    md = render_markdown("tfidf-lr-1", report, agreements)

    assert "macro-F1：**1.000**" in md
    assert "| negative | 0 | 12 | 0 |" in md
    assert "| `groq:q` | 1 | 100.0% |" in md
