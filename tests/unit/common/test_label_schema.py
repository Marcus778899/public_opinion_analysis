from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from radar.common.enums import Polarity
from radar.common.schemas import Label, Sentiment

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def label(*sentiments: Sentiment, labeled_at: datetime = NOW) -> Label:
    return Label(
        post_id="Stock.M.1759730000.A.1B2",
        labeler="gemini-3.8-flash",
        version="prompt-v1",
        labeled_at=labeled_at,
        sentiments=list(sentiments),
    )


WHOLE_NEG = Sentiment(target=None, polarity=Polarity.NEGATIVE)


def test_label_with_whole_post_and_targets_is_valid():
    lbl = label(WHOLE_NEG, Sentiment(target="台積電", polarity=Polarity.POSITIVE))

    assert [s.target for s in lbl.sentiments] == [None, "台積電"]


def test_label_without_whole_post_sentiment_raises():
    with pytest.raises(ValidationError, match="exactly one whole-post"):
        label(Sentiment(target="台積電", polarity=Polarity.POSITIVE))


def test_label_with_two_whole_post_sentiments_raises():
    with pytest.raises(ValidationError, match="exactly one whole-post"):
        label(WHOLE_NEG, Sentiment(target=None, polarity=Polarity.NEUTRAL))


def test_label_duplicate_target_raises():
    with pytest.raises(ValidationError, match="duplicate targets"):
        label(
            WHOLE_NEG,
            Sentiment(target="台積電", polarity=Polarity.POSITIVE),
            Sentiment(target="台積電", polarity=Polarity.NEGATIVE),
        )


def test_label_blank_target_raises():
    with pytest.raises(ValidationError, match="blank"):
        label(WHOLE_NEG, Sentiment(target="  ", polarity=Polarity.POSITIVE))


def test_label_unknown_polarity_raises():
    with pytest.raises(ValidationError):
        Sentiment(target=None, polarity="angry")


def test_label_naive_labeled_at_raises():
    with pytest.raises(ValidationError):
        label(WHOLE_NEG, labeled_at=datetime(2026, 10, 7, 12, 0))
