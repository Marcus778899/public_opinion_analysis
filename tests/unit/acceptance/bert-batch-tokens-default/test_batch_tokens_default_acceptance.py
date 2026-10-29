"""驗收 bert-batch-tokens-default：max_batch_tokens 預設值為 2048。"""

import inspect
import re
from pathlib import Path

from radar.common.settings import InferenceSettings
from radar.ml.training import classifier
from radar.ml.training.classifier import load_classifier

ROOT = Path(__file__).resolve().parents[4]


def test_settings_default_max_batch_tokens_is_2048(monkeypatch):
    monkeypatch.delenv("INFERENCE_MAX_BATCH_TOKENS", raising=False)
    monkeypatch.setenv("INFERENCE_MODEL_DIR", "models/x")

    assert InferenceSettings().max_batch_tokens == 2048


def test_settings_env_overrides_default(monkeypatch):
    monkeypatch.setenv("INFERENCE_MODEL_DIR", "models/x")
    monkeypatch.setenv("INFERENCE_MAX_BATCH_TOKENS", "4096")

    assert InferenceSettings().max_batch_tokens == 4096


def test_default_constant_is_2048():
    assert classifier.DEFAULT_MAX_BATCH_TOKENS == 2048


def test_load_classifier_default_parameter_is_2048():
    param = inspect.signature(load_classifier).parameters["max_batch_tokens"]

    assert param.default == 2048


def test_env_example_documents_2048():
    text = (ROOT / ".env.example").read_text()

    assert re.search(r"^# INFERENCE_MAX_BATCH_TOKENS=2048$", text, re.M)
    assert "預設 2048" in text
    assert "4096" not in text
