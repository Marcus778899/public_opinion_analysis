from datetime import UTC, datetime

import pytest

from radar.common.enums import Polarity
from radar.common.kafka.consumer import TransientError
from radar.common.schemas import CdcPost, Label, Sentiment
from radar.ml.labeling.llm import FallbackLabeler, LabelerError, QuotaExhaustedError
from radar.ml.labeling.prompt import PROMPT_VERSION
from radar.ml.labeling.stream import StreamLabeler, is_new_post, should_sample
from tests.unit.ml.fakes import ScriptedLabeler

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
WHOLE = [Sentiment(target=None, polarity=Polarity.NEGATIVE)]


def event(post_id: str = "Stock.M.1.A.1", op: str | None = "c", deleted: bool = False) -> CdcPost:
    return CdcPost(
        post_id=post_id, board="Stock", title="t", content="c", is_deleted=deleted, op=op
    )


def handler(labeler, percent: int = 100):
    published: list[Label] = []
    flushes: list[int] = []
    h = StreamLabeler(
        FallbackLabeler([labeler]),
        published.append,
        lambda: flushes.append(1),
        now=lambda: NOW,
        percent=percent,
    )
    return h, published, flushes


def test_should_sample_is_deterministic():
    assert [should_sample(f"Stock.M.{i}.A.1") for i in range(50)] == [
        should_sample(f"Stock.M.{i}.A.1") for i in range(50)
    ]


def test_should_sample_rate_close_to_percent():
    hits = sum(should_sample(f"Gossiping.M.{1759730000 + i}.A.{i:03X}") for i in range(20_000))

    assert 0.04 < hits / 20_000 < 0.06


@pytest.mark.parametrize(
    ("op", "expected"), [("c", True), ("u", False), ("r", False), (None, False)]
)
def test_is_new_post_only_create(op, expected):
    assert is_new_post(op) is expected


def test_handler_labels_new_sampled_posts_and_flushes():
    h, published, flushes = handler(ScriptedLabeler(WHOLE, name="groq:q"))

    h([event("a"), event("b", op="u"), event("c", deleted=True)])

    assert [(p.post_id, p.labeler, p.version, p.labeled_at) for p in published] == [
        ("a", "groq:q", PROMPT_VERSION, NOW)
    ]
    assert flushes == [1]


def test_handler_skips_unsampled_posts():
    labeler = ScriptedLabeler(name="groq")
    h, published, _ = handler(labeler, percent=0)

    h([event("a")])

    assert published == [] and labeler.calls == []


def test_handler_labeler_error_skips_post():
    h, published, _ = handler(ScriptedLabeler(LabelerError("blocked"), WHOLE))

    h([event("a"), event("b")])

    assert [p.post_id for p in published] == ["b"]


def test_handler_all_exhausted_raises_transient():
    h, _, _ = handler(ScriptedLabeler(QuotaExhaustedError("daily")))

    with pytest.raises(TransientError):
        h([event("a")])
