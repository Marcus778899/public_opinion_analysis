"""訓練與評估共用的資料格式與讀寫（S3-06）。"""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from radar.common.enums import Polarity


@dataclass(frozen=True)
class Example:
    post_id: str
    board: str
    text: str
    polarity: Polarity


def post_text(title: str | None, content: str | None, max_chars: int) -> str:
    """訓練、評估、推論都用同一個函式組文字，避免三處不一致。"""
    title = (title or "").strip()
    content = (content or "").strip()[:max_chars]
    return f"{title}\n{content}".strip()


def class_counts(examples: list[Example]) -> dict[str, int]:
    counts = Counter(e.polarity.value for e in examples)
    return {p.value: counts.get(p.value, 0) for p in Polarity}


def write_jsonl(path: Path, examples: list[Example]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in examples:
            row = {"post_id": e.post_id, "board": e.board, "text": e.text, "polarity": e.polarity}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[Example]:
    examples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            examples.append(Example(r["post_id"], r["board"], r["text"], Polarity(r["polarity"])))
    return examples
