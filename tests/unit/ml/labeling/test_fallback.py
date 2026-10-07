import pytest

from radar.common.enums import Polarity
from radar.common.schemas import Sentiment
from radar.ml.labeling.llm import AllExhaustedError, FallbackLabeler, QuotaExhaustedError
from tests.unit.ml.fakes import ScriptedLabeler, post

WHOLE = [Sentiment(target=None, polarity=Polarity.NEUTRAL)]


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_fallback_uses_first_labeler_when_available():
    first, second = ScriptedLabeler(WHOLE, name="groq"), ScriptedLabeler(name="gemini")

    assert FallbackLabeler([first, second]).label_named(post()) == ("groq", WHOLE)
    assert second.calls == []


def test_fallback_switches_on_quota_and_reports_actual_labeler():
    first = ScriptedLabeler(QuotaExhaustedError("daily"), name="groq")
    second = ScriptedLabeler(WHOLE, WHOLE, name="gemini")
    labeler = FallbackLabeler([first, second], cooldown_s=60, clock=Clock())

    assert labeler.label_named(post())[0] == "gemini"
    assert labeler.label_named(post())[0] == "gemini"
    assert len(first.calls) == 1  # 冷卻期間不再呼叫


def test_fallback_retries_exhausted_labeler_after_cooldown():
    clock = Clock()
    first = ScriptedLabeler(QuotaExhaustedError("daily"), WHOLE, name="groq")
    second = ScriptedLabeler(WHOLE, name="gemini")
    labeler = FallbackLabeler([first, second], cooldown_s=60, clock=clock)
    labeler.label_named(post())

    clock.t = 61

    assert labeler.label_named(post())[0] == "groq"


def test_fallback_all_exhausted_raises():
    labeler = FallbackLabeler(
        [
            ScriptedLabeler(QuotaExhaustedError("x"), name="a"),
            ScriptedLabeler(QuotaExhaustedError("y"), name="b"),
        ],
        clock=Clock(),
    )

    with pytest.raises(AllExhaustedError):
        labeler.label_named(post())


def test_fallback_requires_labelers():
    with pytest.raises(ValueError):
        FallbackLabeler([])
