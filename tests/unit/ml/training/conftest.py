import pytest

from radar.common.enums import Polarity
from radar.ml.training.dataset import Example

WORDS = {
    Polarity.POSITIVE: ["大漲", "讚讚", "看好", "賺爛"],
    Polarity.NEGATIVE: ["崩盤", "笑死", "爛透", "接刀"],
    Polarity.NEUTRAL: ["請問", "資訊", "公告", "時間"],
}


def synthetic(per_class: int = 12) -> list[Example]:
    """每類用不同的關鍵字組成，模型應能完全分開。"""
    examples = []
    for polarity, words in WORDS.items():
        for i in range(per_class):
            text = f"{words[i % 4]}{words[(i + 1) % 4]} 第{i}篇"
            examples.append(Example(f"Stock.M.{i}.A.{polarity.value}", "Stock", text, polarity))
    return examples


@pytest.fixture
def examples() -> list[Example]:
    return synthetic()
