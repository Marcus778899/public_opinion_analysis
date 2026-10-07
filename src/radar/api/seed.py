"""開發規格 S1-08：透過 API 建立初始看板（冪等，已存在就略過）。

走 HTTP 而不直接寫 PG，維持 FastAPI 是 boards 唯一寫入者（設計文件 4.3）。
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

INITIAL_BOARDS = [
    {"board": "Gossiping", "interval_sec": 60, "recrawl_min_push": 10},
    {"board": "Stock", "interval_sec": 120, "recrawl_min_push": 0},
    {"board": "Tech_Job", "interval_sec": 600, "recrawl_min_push": 0},
]


@dataclass
class SeedResult:
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def seed(api_base_url: str, boards: list[dict], *, timeout_s: float = 10.0) -> SeedResult:
    """POST /boards；409 視為已存在略過，其他錯誤直接拋出。"""
    if not api_base_url.startswith(("http://", "https://")):
        raise ValueError(f"api_base_url must be http(s): {api_base_url!r}")
    url = f"{api_base_url.rstrip('/')}/boards"
    result = SeedResult()
    for board in boards:
        request = urllib.request.Request(
            url,
            data=json.dumps(board).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s):  # nosec B310: scheme 已檢查
                result.created.append(board["board"])
        except urllib.error.HTTPError as e:
            if e.code != 409:
                raise
            result.skipped.append(board["board"])
    return result
