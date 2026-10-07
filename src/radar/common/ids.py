"""PTT 識別碼與網址（開發規格 2.1）：post_id = <board>.<文章檔名>。"""

import re

PTT_BASE_URL = "https://www.ptt.cc"

_BOARD_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_FILENAME_RE = re.compile(r"^M\.\d+\.A\.[0-9A-Fa-f]{3}$")


def make_post_id(board: str, filename: str) -> str:
    """例：make_post_id("Stock", "M.1759730000.A.1B2") -> "Stock.M.1759730000.A.1B2"。"""
    _validate(board, filename)
    return f"{board}.{filename}"


def split_post_id(post_id: str) -> tuple[str, str]:
    """make_post_id 的反函式，回傳 (board, filename)。"""
    board, sep, filename = post_id.partition(".")
    if not sep:
        raise ValueError(f"post_id missing '.': {post_id!r}")
    _validate(board, filename)
    return board, filename


def _validate(board: str, filename: str) -> None:
    if not _BOARD_RE.fullmatch(board):
        raise ValueError(f"invalid board: {board!r}")
    if not _FILENAME_RE.fullmatch(filename):
        raise ValueError(f"invalid PTT filename: {filename!r}")


def is_valid_board(board: str) -> bool:
    return bool(_BOARD_RE.fullmatch(board))


def board_index_url(board: str) -> str:
    """看板最新一頁列表，例："Stock" -> "https://www.ptt.cc/bbs/Stock/index.html"。"""
    if not is_valid_board(board):
        raise ValueError(f"invalid board: {board!r}")
    return f"{PTT_BASE_URL}/bbs/{board}/index.html"
