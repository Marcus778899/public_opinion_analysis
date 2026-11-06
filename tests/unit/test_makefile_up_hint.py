import re
from pathlib import Path

MAKEFILE = Path(__file__).resolve().parents[2] / "Makefile"


def _up_block() -> tuple[str, str]:
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^up: [^\n]*?##([^\n]*)\n((?:\t[^\n]*\n)+)", text, re.MULTILINE)
    assert match, "找不到 up target"
    return match.group(1), match.group(2)


def test_up_說明_提到_connect_unhealthy_與_up_app() -> None:
    hint, _ = _up_block()
    assert "connect" in hint
    assert "unhealthy" in hint
    assert "--wait" in hint
    assert "make up-app" in hint


def test_up_實際指令_維持只起基礎設施並等待() -> None:
    _, recipe = _up_block()
    assert recipe.strip() == "$(COMPOSE) up -d --wait"
