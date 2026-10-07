import pytest

from radar.ml.labeling.factory import build_labeler


@pytest.fixture
def provider_env(monkeypatch):
    for var in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(var, "k")
    for var in ("GEMINI_MODEL", "GROQ_MODEL", "OPENROUTER_MODEL"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize(
    ("provider", "name"),
    [
        ("gemini", "gemini-3.1-flash-lite"),
        ("groq", "groq:qwen/qwen3.8-27b"),
        ("openrouter", "openrouter:google/gemma-4-31b-it:free"),
    ],
)
def test_build_labeler_uses_provider_default_model(provider_env, provider, name):
    labeler = build_labeler(provider, max_chars=100)

    assert labeler.name == name
    labeler.close()


def test_build_labeler_model_override_from_env(provider_env, monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")

    assert build_labeler("groq", max_chars=100).name == "groq:openai/gpt-oss-120b"


def test_build_labeler_unknown_provider_raises():
    with pytest.raises(ValueError, match="unknown labeler provider"):
        build_labeler("nope", max_chars=100)
