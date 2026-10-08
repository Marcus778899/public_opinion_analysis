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


# --- #11：全部額度用完時告知何時可再試 ---


def test_all_exhausted_error_carries_seconds_until_earliest_cooldown_ends():
    clock = Clock()
    a = ScriptedLabeler(QuotaExhaustedError("x"), name="a")
    b = ScriptedLabeler(QuotaExhaustedError("y"), name="b")
    labeler = FallbackLabeler([a, b], cooldown_s=3600, clock=clock)
    with pytest.raises(AllExhaustedError):
        labeler.label_named(post())  # a、b 都在 t=0 開始冷卻
    clock.t = 600

    with pytest.raises(AllExhaustedError) as info:
        labeler.label_named(post())

    assert info.value.retry_after_s == 3000


def test_seconds_until_available_zero_when_a_labeler_is_available():
    clock = Clock()
    a = ScriptedLabeler(QuotaExhaustedError("x"), name="a")
    b = ScriptedLabeler(WHOLE, name="b")
    labeler = FallbackLabeler([a, b], cooldown_s=3600, clock=clock)
    labeler.label_named(post())

    assert labeler.seconds_until_available() == 0
