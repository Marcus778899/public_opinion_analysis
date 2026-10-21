import re
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[3] / "infra" / "grafana" / "Dockerfile"


def _from_args_without_default(text: str) -> list[str]:
    defaults: dict[str, bool] = {}
    for line in text.splitlines():
        m = re.match(r"\s*ARG\s+(\w+)(=(.*))?$", line)
        if m:
            defaults[m.group(1)] = bool(m.group(3))
    missing: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("FROM"):
            for name in re.findall(r"\$\{?(\w+)", line):
                if not defaults.get(name, False):
                    missing.append(name)
    return missing


def test_from_args_in_dockerfile_all_have_default() -> None:
    assert _from_args_without_default(DOCKERFILE.read_text()) == []


def test_from_arg_without_default_is_detected() -> None:
    assert _from_args_without_default("ARG V\nFROM x:${V}\n") == ["V"]


def test_from_arg_with_default_is_accepted() -> None:
    assert _from_args_without_default("ARG V=1\nFROM x:${V}\n") == []
