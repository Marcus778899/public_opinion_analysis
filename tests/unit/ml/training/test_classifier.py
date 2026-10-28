from datetime import UTC, datetime
from pathlib import Path

import pytest

from radar.common.enums import Polarity
from radar.ml.training.classifier import (
    OnnxClassifier,
    SklearnClassifier,
    load_classifier,
    top_class,
)
from radar.ml.training.train import ModelCard, ModelKind, build_pipeline, save_model, train
from tests.helpers.onnx_model import build_model_dir


def test_top_class_returns_highest_score():
    scores = {Polarity.POSITIVE: 0.1, Polarity.NEGATIVE: 0.2, Polarity.NEUTRAL: 0.7}
    assert top_class(scores) is Polarity.NEUTRAL


def test_top_class_tie_takes_first_declared():
    assert top_class(dict.fromkeys(Polarity, 0.5)) is list(Polarity)[0]


def test_sklearn_classifier_returns_all_classes_summing_to_one(examples):
    clf = SklearnClassifier(train(examples, seed=42))

    [scores] = clf.predict_proba([examples[0].text])

    assert set(scores) == set(Polarity)
    assert sum(scores.values()) == pytest.approx(1.0)
    assert top_class(scores) is examples[0].polarity


def test_sklearn_classifier_fills_missing_class_with_zero(examples):
    two = [e for e in examples if e.polarity is not Polarity.NEUTRAL]
    pipeline = build_pipeline(seed=0)
    pipeline.set_params(tfidf__min_df=1)
    clf = SklearnClassifier(pipeline.fit([e.text for e in two], [e.polarity.value for e in two]))

    [scores] = clf.predict_proba([two[0].text])

    assert scores[Polarity.NEUTRAL] == 0.0
    assert sum(scores.values()) == pytest.approx(1.0)


def test_sklearn_classifier_empty_input_returns_empty_list(examples):
    assert SklearnClassifier(train(examples, seed=42)).predict_proba([]) == []


def test_load_classifier_sklearn_dir_returns_sklearn_classifier(examples, tmp_path: Path):
    card = ModelCard(
        model_version="tfidf-lr-202610010000",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        dataset="d",
        labeler="groq",
        label_version="v",
        max_chars=2000,
        n_train=36,
        class_counts={},
        params={},
    )
    model_dir = save_model(train(examples, seed=42), card, tmp_path)

    clf, loaded = load_classifier(model_dir, threads=1)

    assert isinstance(clf, SklearnClassifier)
    assert loaded.kind is ModelKind.SKLEARN


def test_load_classifier_onnx_dir_returns_onnx_classifier(tmp_path: Path):
    model_dir = build_model_dir(tmp_path / "bert-test-202610210000")

    clf, card = load_classifier(model_dir, threads=1)

    assert isinstance(clf, OnnxClassifier)
    assert card.kind is ModelKind.ONNX


def test_onnx_classifier_without_max_len_is_rejected(tmp_path: Path):
    model_dir = build_model_dir(tmp_path / "bert-test-202610210000")
    _, card = load_classifier(model_dir, threads=1)
    card = card.model_copy(update={"max_len": None})

    with pytest.raises(ValueError, match="max_len"):
        OnnxClassifier(model_dir, card, threads=1)


def test_load_classifier_missing_card_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_classifier(tmp_path, threads=1)


def test_onnx_scores_follow_keywords(tmp_path: Path):
    clf, _ = load_classifier(build_model_dir(tmp_path / "bert-test-202610210000"), threads=1)

    results = clf.predict_proba(["今天好棒", "爛糟慘"])

    assert [top_class(s) for s in results] == [Polarity.POSITIVE, Polarity.NEGATIVE]


def test_onnx_chunks_group_by_length_within_token_limit(tmp_path: Path):
    model_dir = build_model_dir(tmp_path / "bert-test-202610210000", max_len=32)
    clf, _ = load_classifier(model_dir, threads=1, max_batch_tokens=64)
    assert isinstance(clf, OnnxClassifier)

    chunks = clf._chunks([0, 1, 2, 3, 4], [4, 4, 30, 32, 32])

    assert chunks == [[0, 1], [2, 3], [4]]


def test_onnx_max_batch_tokens_below_max_len_is_rejected(tmp_path: Path):
    model_dir = build_model_dir(tmp_path / "bert-test-202610210000", max_len=32)

    with pytest.raises(ValueError, match="max_batch_tokens"):
        load_classifier(model_dir, threads=1, max_batch_tokens=31)
