from radar.common.enums import Polarity
from radar.ml.training.dataset import Example, class_counts, post_text, read_jsonl, write_jsonl


def test_post_text_joins_title_and_truncated_content():
    assert post_text(" 標題 ", "一二三四五", 3) == "標題\n一二三"


def test_post_text_missing_parts():
    assert post_text(None, "內文", 10) == "內文"
    assert post_text("標題", None, 10) == "標題"
    assert post_text(None, None, 10) == ""


def test_jsonl_roundtrip(tmp_path):
    examples = [Example("a", "Stock", "台積電\n大漲", Polarity.POSITIVE)]
    path = tmp_path / "d" / "x.jsonl"

    write_jsonl(path, examples)

    assert read_jsonl(path) == examples
    assert "台積電" in path.read_text()


def test_class_counts_includes_zero_classes():
    examples = [Example("a", "S", "t", Polarity.NEGATIVE)]

    assert class_counts(examples) == {"positive": 0, "negative": 1, "neutral": 0}
