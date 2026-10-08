from pathlib import Path

import pytest

from radar.common.enums import Polarity
from radar.ml.labeling.prompt import (
    PROMPT_VERSION,
    RULES,
    LabelParseError,
    PostText,
    build_prompt,
    parse_sentiments,
)

POST = PostText("Stock.M.1759730000.A.1B2", "Stock", "[新聞] 台積電法說", "營收創新高")


def test_build_prompt_includes_title_and_content():
    prompt = build_prompt(POST, max_chars=2000)

    assert "PTT Stock 板" in prompt
    assert "標題：[新聞] 台積電法說" in prompt
    assert "營收創新高" in prompt
    assert "截斷" not in prompt.split("內文：")[1]


def test_build_prompt_truncates_long_content_and_marks_it():
    post = PostText(POST.post_id, "Stock", "t", "一二三四五六七八九十")

    prompt = build_prompt(post, max_chars=4)

    body = prompt.split("內文：\n")[1]
    assert body.startswith("一二三四\n")
    assert "五" not in body
    assert body.endswith("（內文過長，以上已截斷）")


def test_build_prompt_handles_missing_title_and_content():
    prompt = build_prompt(PostText(POST.post_id, "Stock", None, None), max_chars=10)

    assert "（無標題）" in prompt
    assert "（無內文）" in prompt


def test_parse_sentiments_valid_json():
    raw = (
        '{"sentiments": [{"target": null, "polarity": "negative"},'
        ' {"target": "台積電", "polarity": "positive"}]}'
    )

    parsed = parse_sentiments(raw)

    assert [(s.target, s.polarity) for s in parsed] == [
        (None, Polarity.NEGATIVE),
        ("台積電", Polarity.POSITIVE),
    ]


def test_parse_sentiments_blank_target_becomes_whole_post():
    parsed = parse_sentiments('{"sentiments": [{"target": "  ", "polarity": "neutral"}]}')

    assert [(s.target, s.polarity) for s in parsed] == [(None, Polarity.NEUTRAL)]


@pytest.mark.parametrize(
    "raw",
    ["not json", '{"other": []}', '{"sentiments": [{"target": null, "polarity": "angry"}]}'],
)
def test_parse_sentiments_invalid_json_raises(raw):
    with pytest.raises(LabelParseError):
        parse_sentiments(raw)


def test_parse_sentiments_missing_whole_post_raises():
    with pytest.raises(LabelParseError, match="whole-post"):
        parse_sentiments('{"sentiments": [{"target": "台積電", "polarity": "positive"}]}')


GUIDELINE = Path(__file__).resolve().parents[4] / "docs/labeling-guideline.md"


def test_rules_match_labeling_guideline_document():
    doc = GUIDELINE.read_text()

    for i, rule in enumerate(RULES, start=1):
        assert f"{i}. {rule}" in doc, f"rule {i} differs from docs/labeling-guideline.md"
    assert f"版本：{PROMPT_VERSION}" in doc


def test_build_prompt_lists_every_rule():
    prompt = build_prompt(POST, max_chars=2000)

    assert all(rule in prompt for rule in RULES)
