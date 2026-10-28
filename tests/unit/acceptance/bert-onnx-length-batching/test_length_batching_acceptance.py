"""驗收 bert-onnx-length-batching（開發規格 7.27「修正單」）：只走對外行為。

以 onnxruntime.InferenceSession 的替身記錄每次 run 的輸入形狀，不碰內部屬性。
"""

import sys
from pathlib import Path

import onnxruntime
import pytest

# NOTE: 目錄名含連字號，不能放 __init__.py；補上 rootdir 才能 import tests.*
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tests.helpers.onnx_model import build_model_dir

from radar.common.settings import InferenceSettings
from radar.ml.inference import main as inference_main
from radar.ml.training import evaluate as evaluate_module
from radar.ml.training.classifier import load_classifier

MAX_LEN = 32
BIG = 10_000_000

# 長短交錯，含超過 max_len 會被截斷的長文
TEXTS = [
    "好",
    "今天好棒好棒好棒好棒好棒好棒好棒好棒好棒好棒好棒好棒好棒好棒好棒好棒好棒好棒",
    "爛糟",
    "今天的公告請問" * 2,
    "慘",
    "今天好棒",
    "爛糟慘崩" * 10,
    "公告",
    "請問今天的公告好棒" * 3,
    "崩",
    "今",
    "好棒讚漲" * 2,
]


class Stop(BaseException):
    pass


@pytest.fixture
def model_dir(tmp_path):
    return build_model_dir(tmp_path / "bert-test-x", max_len=MAX_LEN)


@pytest.fixture
def run_shapes(monkeypatch):
    shapes: list[tuple[int, int]] = []
    real = onnxruntime.InferenceSession

    class Recording(real):  # type: ignore[valid-type, misc]
        def run(self, output_names, input_feed, *args, **kwargs):
            rows, length = input_feed["input_ids"].shape
            shapes.append((rows, length))
            return super().run(output_names, input_feed, *args, **kwargs)

    monkeypatch.setattr(onnxruntime, "InferenceSession", Recording)
    return shapes


def _probs(model_dir, texts, limit):
    clf, _ = load_classifier(model_dir, threads=1, max_batch_tokens=limit)
    return clf.predict_proba(texts)


def test_small_batches_match_single_batch_probabilities_and_order(model_dir):
    whole = _probs(model_dir, TEXTS, BIG)
    split = _probs(model_dir, TEXTS, 64)

    assert len(split) == len(TEXTS)
    for a, b in zip(whole, split, strict=True):
        assert set(a) == set(b)
        for label in a:
            assert abs(a[label] - b[label]) < 1e-5


def test_output_order_follows_input_even_when_reversed(model_dir):
    forward = _probs(model_dir, TEXTS, 64)
    backward = _probs(model_dir, list(reversed(TEXTS)), 64)

    for a, b in zip(forward, reversed(backward), strict=True):
        for label in a:
            assert abs(a[label] - b[label]) < 1e-5


def test_every_run_stays_within_token_limit(model_dir, run_shapes):
    limit = 100
    _probs(model_dir, TEXTS, limit)

    assert len(run_shapes) > 1
    assert sum(rows for rows, _ in run_shapes) == len(TEXTS)
    assert all(rows * length <= limit for rows, length in run_shapes)


def test_single_text_over_limit_runs_alone(model_dir, run_shapes):
    # max_len 32：長文序列 32，上限 32 時任何兩篇都超過，每篇各自一批
    _probs(model_dir, TEXTS, MAX_LEN)

    assert all(rows == 1 for rows, length in run_shapes if length >= MAX_LEN)
    assert sum(rows for rows, _ in run_shapes) == len(TEXTS)


def test_large_limit_runs_single_batch(model_dir, run_shapes):
    _probs(model_dir, TEXTS, BIG)

    assert len(run_shapes) == 1
    assert run_shapes[0][0] == len(TEXTS)


def test_empty_input_returns_empty_without_running(model_dir, run_shapes):
    assert _probs(model_dir, [], 64) == []
    assert run_shapes == []


def test_limit_below_card_max_len_is_rejected(model_dir):
    with pytest.raises(ValueError):
        load_classifier(model_dir, threads=1, max_batch_tokens=MAX_LEN - 1)


def test_limit_equal_to_max_len_is_accepted(model_dir):
    clf, _ = load_classifier(model_dir, threads=1, max_batch_tokens=MAX_LEN)
    assert len(clf.predict_proba(["今天好棒"])) == 1


def test_max_batch_tokens_is_keyword_only(model_dir):
    with pytest.raises(TypeError):
        load_classifier(model_dir, 1, 64)  # type: ignore[misc]


def test_settings_default_max_batch_tokens_is_4096(monkeypatch):
    monkeypatch.delenv("INFERENCE_MAX_BATCH_TOKENS", raising=False)
    monkeypatch.setenv("INFERENCE_MODEL_DIR", "models/x")

    assert InferenceSettings().max_batch_tokens == 4096


def test_settings_reads_max_batch_tokens_from_env(monkeypatch):
    monkeypatch.setenv("INFERENCE_MODEL_DIR", "models/x")
    monkeypatch.setenv("INFERENCE_MAX_BATCH_TOKENS", "8192")

    assert InferenceSettings().max_batch_tokens == 8192


def test_inference_main_passes_setting_to_load_classifier(monkeypatch):
    monkeypatch.setenv("INFERENCE_MODEL_DIR", "models/x")
    monkeypatch.setenv("INFERENCE_MAX_BATCH_TOKENS", "8192")
    seen: dict[str, object] = {}

    def fake_load(*_a, **kwargs):
        seen.update(kwargs)
        raise Stop

    monkeypatch.setattr(inference_main, "load_classifier", fake_load)
    with pytest.raises(Stop):
        inference_main.main()

    assert seen["max_batch_tokens"] == 8192


def test_evaluate_main_passes_setting_to_load_classifier(monkeypatch, tmp_path):
    monkeypatch.setenv("INFERENCE_MAX_BATCH_TOKENS", "8192")
    seen: dict[str, object] = {}

    def fake_load(*_a, **kwargs):
        seen.update(kwargs)
        raise Stop

    monkeypatch.setattr(evaluate_module, "load_classifier", fake_load)
    monkeypatch.setattr(sys, "argv", ["evaluate", "--model", str(tmp_path)])
    with pytest.raises(Stop):
        evaluate_module.main()

    assert seen["max_batch_tokens"] == 8192
