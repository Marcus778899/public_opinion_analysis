"""bert-evaluate-report-fix 驗收：經 evaluate.main() 檢查 evaluation.md（開發規格 7.27）。"""

import sys
from types import SimpleNamespace

import pytest
from tests.unit.ml.fakes import FakeClassifier

from radar.common.enums import Polarity
from radar.ml.labeling.manual import MANUAL_LABELER
from radar.ml.training import evaluate as ev

LLM = "groq:fake-model"
LABEL_VERSION = "prompt-v6"
LOAD_RSS = 111.0
LATER_RSS = 999.0


@pytest.fixture
def run_main(monkeypatch, tmp_path):
    def _run(llm_labels: dict[str, dict[str, Polarity]]) -> str:
        pids = ["Stock.M.1.A.001", "Stock.M.2.A.002", "Stock.M.3.A.003"]
        card = SimpleNamespace(
            model_version="bert-x",
            label_version=LABEL_VERSION,
            labeler=LLM,
            max_chars=500,
            metrics={},
        )
        rss_calls: list[str] = []
        loaded = {"done": False}

        def fake_load(*_a, **_k):
            loaded["done"] = True
            return FakeClassifier(), card

        def fake_rss() -> float:
            rss_calls.append("x")
            return LOAD_RSS if loaded["done"] and len(rss_calls) == 1 else LATER_RSS

        human = {
            pid: SimpleNamespace(
                sentiments=[SimpleNamespace(target=None, polarity=Polarity.NEGATIVE)]
            )
            for pid in pids
        }
        posts = {pid: SimpleNamespace(board="Stock", title="t", content="c") for pid in pids}
        monkeypatch.setattr(ev, "load_classifier", fake_load)
        monkeypatch.setattr(ev, "_peak_rss_mb", fake_rss)
        monkeypatch.setattr(ev, "load_human_labels", lambda _d: human)
        monkeypatch.setattr(ev, "fetch_posts", lambda _ch, _ids: posts)
        monkeypatch.setattr(
            ev, "fetch_whole_post_labels", lambda _ch, name, _v: llm_labels.get(name, {})
        )
        monkeypatch.setattr(ev, "ClickHouseClient", lambda _s: SimpleNamespace(close=lambda: None))
        monkeypatch.setattr(ev, "ClickHouseSettings", lambda: None)
        monkeypatch.setattr(ev, "write_card", lambda *_a, **_k: None)
        monkeypatch.setattr(sys, "argv", ["evaluate", "--model", str(tmp_path)])
        ev.main()
        return (tmp_path / ev.REPORT_FILE).read_text()

    return _run


def test_report_score_section_title_is_model_scores(run_main):
    md = run_main({MANUAL_LABELER: {}})

    assert "## 模型分數" in md
    assert "## Baseline" not in md


def test_zero_overlap_labeler_has_note_instead_of_zero_rows(run_main):
    md = run_main({MANUAL_LABELER: {"Stock.M.1.A.001": Polarity.NEGATIVE}})

    assert f"`{LLM}` 在人工測試集沒有 `{LABEL_VERSION}` 的標註" in md
    assert f"| `{LLM}` |" not in md


def test_labeler_with_overlap_keeps_rows_and_has_no_note(run_main):
    labels = {
        "Stock.M.1.A.001": Polarity.NEGATIVE,
        "Stock.M.2.A.002": Polarity.POSITIVE,
    }
    md = run_main({LLM: labels, MANUAL_LABELER: labels})

    assert f"| `{LLM}` | 整體 | 2 |" in md
    assert f"| `{MANUAL_LABELER}` | 整體 | 2 |" in md
    assert "在人工測試集沒有" not in md


def test_zero_overlap_report_does_not_list_zero_row_for_board(run_main):
    md = run_main({MANUAL_LABELER: {"Stock.M.1.A.001": Polarity.NEGATIVE}})

    assert f"| `{LLM}` | 整體 | 0 |" not in md
    assert f"| `{LLM}` | Stock" not in md


def test_runtime_section_has_rss_after_model_load(run_main):
    md = run_main({MANUAL_LABELER: {}})

    assert "| 載入模型後 RSS | 111 MB |" in md
    assert "| 記憶體峰值（RSS） | 999 MB |" in md
