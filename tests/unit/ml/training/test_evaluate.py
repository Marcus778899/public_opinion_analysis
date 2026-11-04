import pytest

from radar.common.enums import Polarity
from radar.ml.training import evaluate as evaluate_module
from radar.ml.training.classifier import SklearnClassifier
from radar.ml.training.dataset import Example
from radar.ml.training.evaluate import (
    RuntimeStats,
    agreements_by_board,
    evaluate_by_board,
    evaluate_model,
    llm_vs_human,
    render_markdown,
)
from radar.ml.training.train import train
from tests.unit.ml.fakes import FakeClassifier

POS, NEU, NEG = Polarity.POSITIVE, Polarity.NEUTRAL, Polarity.NEGATIVE


def test_evaluate_model_macro_f1_and_confusion(examples):
    pipeline = SklearnClassifier(train(examples, seed=42))

    report = evaluate_model(pipeline, examples)

    assert report.n == 36
    assert report.macro_f1 == pytest.approx(1.0)
    assert report.confusion[NEG] == {POS: 0, NEG: 12, NEU: 0}


def test_evaluate_model_empty_raises(examples):
    with pytest.raises(ValueError, match="empty"):
        evaluate_model(SklearnClassifier(train(examples, seed=42)), [])


def test_llm_vs_human_only_overlap():
    agreement = llm_vs_human(
        "groq:q", {"a": NEG, "b": POS, "c": NEU}, {"a": NEG, "b": NEU, "x": POS}
    )

    assert (agreement.labeler, agreement.n, agreement.accuracy) == ("groq:q", 2, 0.5)


def test_llm_vs_human_no_overlap():
    agreement = llm_vs_human("x", {"a": NEG}, {"b": NEG})

    assert (agreement.n, agreement.accuracy, agreement.cohen_kappa) == (0, 0.0, 0.0)


def test_render_markdown_lists_agreements(examples):
    report = evaluate_model(SklearnClassifier(train(examples, seed=42)), examples)
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
    pipeline = SklearnClassifier(train(examples, seed=42))

    reports = evaluate_by_board(pipeline, two_boards(examples))

    assert {b: r.n for b, r in reports.items()} == {"Stock": 36, "Tech_Job": 6}


def test_evaluate_by_board_sorted_by_board_name(examples):
    pipeline = SklearnClassifier(train(examples, seed=42))
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
    pipeline = SklearnClassifier(train(examples, seed=42))
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
    pipeline = SklearnClassifier(train(examples, seed=42))
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


def test_evaluate_model_uses_classifier_top_class(examples):
    report = evaluate_model(FakeClassifier(), examples)  # 一律預測 negative

    assert report.confusion[POS] == {POS: 0, NEG: 12, NEU: 0}
    assert report.per_class_f1[NEG] == pytest.approx(0.5)


def _ticking_clock(step: float):
    state = {"t": 0.0}

    def clock() -> float:
        state["t"] += step
        return state["t"]

    return clock


def test_measure_runtime_computes_percentiles_from_clock(monkeypatch):
    monkeypatch.setattr(evaluate_module, "_clock", _ticking_clock(2.0))
    monkeypatch.setattr(evaluate_module, "_peak_rss_mb", lambda: 123.0)

    stats = evaluate_module.measure_runtime(
        FakeClassifier(), [str(i) for i in range(5)], batch_size=2, threads=3
    )

    # 每批固定 2 秒；批次大小 2、2、1 篇 → 每篇 1000、1000、1000、1000、2000 ms
    assert stats == RuntimeStats(
        threads=3,
        batch_size=2,
        per_post_p50_ms=1000.0,
        per_post_p95_ms=2000.0,
        per_batch_p50_s=2.0,
        per_batch_max_s=2.0,
        peak_rss_mb=123.0,
    )


def test_measure_runtime_warms_up_without_timing(monkeypatch):
    fake = FakeClassifier()
    monkeypatch.setattr(evaluate_module, "_clock", _ticking_clock(1.0))

    evaluate_module.measure_runtime(fake, ["a", "b", "c"], batch_size=2, threads=1)

    assert fake.calls == [["a", "b"], ["a", "b"], ["c"]]


@pytest.mark.parametrize(("texts", "batch_size"), [([], 2), (["a"], 0)])
def test_measure_runtime_rejects_empty_texts_and_bad_batch_size(texts, batch_size):
    with pytest.raises(ValueError):
        evaluate_module.measure_runtime(FakeClassifier(), texts, batch_size=batch_size, threads=1)


def test_peak_rss_mb_is_positive():
    assert evaluate_module._peak_rss_mb() > 0


def test_render_markdown_includes_runtime_section_when_given(examples):
    report = evaluate_model(SklearnClassifier(train(examples, seed=42)), examples)
    runtime = RuntimeStats(2, 100, 12.345, 20.0, 1.234, 2.5, 812.4)

    md = render_markdown("v", report, [], board_reports={}, board_agreements={}, runtime=runtime)

    assert "INFERENCE_THREADS = 2，每批 100 篇。" in md
    assert "| 每篇 p50 | 12.35 ms |" in md
    assert "| 每篇 p95 | 20.00 ms |" in md
    assert "| 每批 p50 | 1.234 s |" in md
    assert "| 每批最大 | 2.500 s |" in md
    assert "| 記憶體峰值（RSS） | 812 MB |" in md


def test_render_markdown_without_runtime_has_no_runtime_section(examples):
    report = evaluate_model(SklearnClassifier(train(examples, seed=42)), examples)

    md = render_markdown("v", report, [], board_reports={}, board_agreements={})

    assert "CPU 推論耗時" not in md


def test_evaluate_model_predicts_in_batches_of_batch_size(examples):
    fake = FakeClassifier()

    report = evaluate_model(fake, examples, batch_size=10)

    assert report.n == 36
    assert [len(c) for c in fake.calls] == [10, 10, 10, 6]


def test_evaluate_by_board_passes_batch_size_through(examples):
    fake = FakeClassifier()

    evaluate_by_board(fake, two_boards(examples), batch_size=7)

    assert fake.calls and all(0 < len(c) <= 7 for c in fake.calls)


def test_evaluate_model_rejects_bad_batch_size(examples):
    with pytest.raises(ValueError, match="batch_size"):
        evaluate_model(FakeClassifier(), examples, batch_size=0)


def test_render_markdown_runtime_with_load_rss_has_extra_row(examples):
    report = evaluate_model(SklearnClassifier(train(examples, seed=42)), examples)
    runtime = RuntimeStats(2, 100, 1.0, 2.0, 1.0, 2.0, 812.4, load_rss_mb=300.2)

    md = render_markdown("v", report, [], board_reports={}, board_agreements={}, runtime=runtime)

    assert "| 載入模型後 RSS | 300 MB |" in md


def test_render_markdown_runtime_without_load_rss_omits_row(examples):
    report = evaluate_model(SklearnClassifier(train(examples, seed=42)), examples)
    runtime = RuntimeStats(2, 100, 1.0, 2.0, 1.0, 2.0, 812.4)

    md = render_markdown("v", report, [], board_reports={}, board_agreements={}, runtime=runtime)

    assert "載入模型後 RSS" not in md


def test_render_markdown_zero_overlap_labeler_gets_note_not_row(examples):
    report = evaluate_model(SklearnClassifier(train(examples, seed=42)), examples)
    agreements = [llm_vs_human("groq:q", {"a": NEG}, {"b": NEG})]

    md = render_markdown(
        "v", report, agreements, board_reports={}, board_agreements={}, label_version="prompt-v6"
    )

    assert "`groq:q` 在人工測試集沒有 `prompt-v6` 的標註" in md
    assert "| `groq:q` |" not in md
    assert "## 模型分數" in md


def test_check_model_dir_rejects_missing_dir(tmp_path):
    import pytest

    from radar.ml.training.evaluate import check_model_dir

    with pytest.raises(SystemExit):
        check_model_dir(tmp_path / "nope")
    check_model_dir(tmp_path)
