"""D-026 revision allowlist 的邊界：變數名最後一段必須是 rev/revision/commit/sha。"""

import re
import tomllib
from pathlib import Path

import pytest

CONFIG = Path(__file__).resolve().parents[2] / ".gitleaks.toml"
HEX40 = "a986e004d2a7f2a1c2f5a3edef4e20604a974e2b"


def _revision_regex() -> re.Pattern[str]:
    data = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    entry = next(a for a in data["allowlists"] if "D-026" in a["description"])
    # NOTE: gitleaks 用 Go RE2；(?i:...) 群組在 Python re 同樣有效
    return re.compile(entry["regexes"][0])


@pytest.mark.parametrize(
    "line",
    [
        f'MACBERT_REVISION = "{HEX40}"',
        f'MACBERT_REV = "{HEX40}"',
        f'CKIP_PR_COMMIT = "{HEX40}"',
        f"rev={HEX40}",
        f"sha: {HEX40}",
        f"commit_sha={HEX40}",
        f"COMMIT_SHA='{HEX40}'",
        f'"revision": "{HEX40}"',
    ],
)
def test_revision_variable_with_hex40_is_allowed(line: str) -> None:
    assert _revision_regex().search(line)


@pytest.mark.parametrize(
    "line",
    [
        f"SHARED_SECRET={HEX40}",
        f'PREVIOUS_API_KEY = "{HEX40}"',
        f"REVOKE_TOKEN={HEX40}",
        f"SHARED_SECRET_SHA_KEY={HEX40}",
        f"SECRETSHA={HEX40}",
        f"revision_token={HEX40}",
    ],
)
def test_secret_name_containing_rev_substring_is_not_allowed(line: str) -> None:
    assert not _revision_regex().search(line)


def test_revision_value_not_40_hex_is_not_allowed() -> None:
    assert not _revision_regex().search(f"rev={HEX40[:39]}")
    assert not _revision_regex().search(f"rev={HEX40}0")
