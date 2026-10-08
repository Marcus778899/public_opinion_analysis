from datetime import UTC, datetime, timedelta, timezone

import pytest

from radar.ml.training.train import (
    ModelCard,
    load_model,
    model_version,
    save_model,
    train,
)
from tests.unit.ml.training.conftest import synthetic

NOW = datetime(2026, 10, 7, 12, 30, tzinfo=UTC)


def card(version: str = "tfidf-lr-202610071230") -> ModelCard:
    return ModelCard(
        model_version=version,
        created_at=NOW,
        dataset="d.jsonl",
        labeler="groq:q",
        label_version="prompt-v4",
        max_chars=2000,
        n_train=36,
        class_counts={"positive": 12, "negative": 12, "neutral": 12},
        params={"seed": 42},
    )


def test_train_fits_and_predicts_known_classes(examples):
    pipeline = train(examples, seed=42)

    assert list(pipeline.predict(["大漲讚讚", "崩盤笑死", "請問資訊"])) == [
        "positive",
        "negative",
        "neutral",
    ]


def test_train_too_few_examples_raises():
    with pytest.raises(ValueError, match="at least 10"):
        train(synthetic(per_class=9), seed=42)


def test_model_version_format_in_utc():
    taipei = timezone(timedelta(hours=8))

    assert model_version(datetime(2026, 10, 7, 20, 30, tzinfo=taipei)) == "tfidf-lr-202610071230"


def test_save_and_load_model_roundtrip(tmp_path, examples):
    pipeline = train(examples, seed=42)

    path = save_model(pipeline, card(), tmp_path)
    loaded, loaded_card = load_model(path)

    assert path == tmp_path / "tfidf-lr-202610071230"
    assert loaded_card == card()
    assert list(loaded.predict(["崩盤笑死"])) == ["negative"]


def test_save_model_refuses_existing_dir(tmp_path, examples):
    pipeline = train(examples, seed=42)
    save_model(pipeline, card(), tmp_path)

    with pytest.raises(FileExistsError):
        save_model(pipeline, card(), tmp_path)
