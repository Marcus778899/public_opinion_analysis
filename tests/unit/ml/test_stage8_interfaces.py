"""階段 8 平行各單之間的介面（開發規格 7.27 檔案分工）：簽名改了要先改設計，再同步這裡。"""

import inspect
from dataclasses import fields

import pytest

from radar.ml.training import classifier, compare, evaluate, import_model
from tests.helpers.onnx_model import PACKAGE_FILES, model_version_for


def params(func) -> list[str]:
    return list(inspect.signature(func).parameters)


@pytest.mark.parametrize(
    ("func", "expected"),
    [
        (classifier.load_classifier, ["model_dir", "threads"]),
        (classifier.top_class, ["scores"]),
        (evaluate.measure_runtime, ["classifier", "texts", "batch_size", "threads"]),
        (import_model.import_model, ["zip_path", "models_dir"]),
        (compare.fetch_pairs, ["client", "a", "b", "since", "labeler", "label_version"]),
        (compare.fetch_latency, ["client", "model_version", "role", "since"]),
        (compare.agreement, ["pairs"]),
        (compare.confidence_buckets, ["scores"]),
        (compare.write_disagreements, ["path", "pairs"]),
    ],
)
def test_cross_task_function_signatures(func, expected):
    assert params(func) == expected


def test_threads_is_keyword_only_for_loading_and_runtime():
    for func in (classifier.load_classifier, evaluate.measure_runtime):
        kind = inspect.signature(func).parameters["threads"].kind
        assert kind is inspect.Parameter.KEYWORD_ONLY


def test_import_whitelist_matches_test_package_files():
    assert frozenset(PACKAGE_FILES) == import_model.ALLOWED_FILES


@pytest.mark.parametrize("quantized", [False, True])
def test_notebook_model_version_naming_passes_import_pattern(quantized):
    for base in ("macbert", "ckip"):
        assert import_model.MODEL_VERSION_RE.fullmatch(model_version_for(quantized, base=base))


@pytest.mark.parametrize("bad", ["../x", "Bert-X", "-bert", "a" * 65, "bert_x", ""])
def test_model_version_pattern_rejects_path_and_odd_names(bad):
    assert import_model.MODEL_VERSION_RE.fullmatch(bad) is None


def test_package_size_limit_is_2gb():
    assert import_model.MAX_TOTAL_BYTES == 2 * 1024**3


def test_compare_result_types_have_expected_fields():
    assert [f.name for f in fields(compare.LatencyStats)] == ["n", "p50_s", "p95_s", "max_s"]
    assert [f.name for f in fields(compare.ConfidenceBucket)] == [
        "threshold",
        "below_ratio",
        "accuracy_vs_llm",
        "n_vs_llm",
    ]
    assert "llm" in {f.name for f in fields(compare.PairedPrediction)}
