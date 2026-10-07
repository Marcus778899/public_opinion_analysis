"""PTT 網頁版（www.ptt.cc）列表頁與文章頁的解析。只處理 HTML，不發請求。"""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlparse
from uuid import UUID

from selectolax.lexbor import LexborHTMLParser, LexborNode

from radar.collector.parsers.ptt_time import (
    created_at_from_filename,
    parse_article_time,
    parse_comment_time,
)
from radar.common.enums import CommentType
from radar.common.ids import PTT_BASE_URL, make_post_id, split_post_id
from radar.common.schemas import RawComment, RawPost

# 列表頁推文數的特殊值：「爆」代表 >= 100，「X1」～「X9」、「XX」代表噓多於推
LIST_PUSH_BOOM = 100
LIST_PUSH_XX = -100

_POST_PATH_RE = re.compile(r"^/bbs/([A-Za-z0-9_-]+)/(M\.\d+\.A\.[0-9A-Fa-f]{3})\.html$")
_LIST_PUSH_X_RE = re.compile(r"^X(\d)$")
_COMMENT_TYPES = {"推": CommentType.PUSH, "噓": CommentType.BOO, "→": CommentType.ARROW}
_FOOTER_MARK = "※ 發信站"
_SIGNATURE_SEP = "\n--\n"


@dataclass(frozen=True)
class ListEntry:
    """列表頁的一列。被刪除的文章沒有連結，post_id 與 url 為 None。"""

    post_id: str | None
    url: str | None
    title: str
    author: str | None
    list_push: int
    is_deleted: bool

    @property
    def is_boom(self) -> bool:
        return self.list_push >= LIST_PUSH_BOOM


@dataclass(frozen=True)
class ListPage:
    entries: list[ListEntry]
    # 「‹ 上頁」的絕對網址；已是第一頁時為 None
    prev_page_url: str | None


class ParseError(ValueError):
    """頁面結構不符預期（PTT 改版、被導到 over18 確認頁等）；由呼叫端送 DLQ。"""


def parse_list_page(html: str, board: str) -> ListPage:
    """只回傳置底分隔線（r-list-sep）以上的文章，置底公告不列入。"""
    tree = LexborHTMLParser(html)
    container = tree.css_first("div.r-list-container")
    if container is None:
        raise ParseError(f"{board}: list container not found (over18 page or layout change?)")
    entries: list[ListEntry] = []
    for node in container.css("div.r-ent, div.r-list-sep"):
        if "r-list-sep" in _classes(node):
            break
        entries.append(_parse_list_entry(node))
    return ListPage(entries=entries, prev_page_url=_prev_page_url(tree))


def parse_list_push(text: str) -> int:
    """列表頁推文數欄位：""→0、"12"→12、"爆"→100、"X3"→-30、"XX"→-100。"""
    text = text.strip()
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    if text == "爆":
        return LIST_PUSH_BOOM
    if text == "XX":
        return LIST_PUSH_XX
    if match := _LIST_PUSH_X_RE.fullmatch(text):
        return -10 * int(match.group(1))
    raise ParseError(f"unknown list push count: {text!r}")


def parse_post_page(
    html: str, *, board: str, url: str, crawled_at: datetime, task_id: UUID
) -> RawPost:
    """文章頁 → RawPost；push_count / boo_count 由推文計算，不用列表頁的數字。"""
    post_id = post_id_from_url(url)
    main = LexborHTMLParser(html).css_first("#main-content")
    if main is None:
        raise ParseError(f"{post_id}: main-content not found (over18 page or layout change?)")
    meta = _parse_meta(main)
    created_at = parse_article_time(meta.get("時間", "")) or created_at_from_filename(
        split_post_id(post_id)[1]
    )
    comments = _parse_comments(main, created_at)
    counts = Counter(c.type for c in comments)
    return RawPost(
        task_id=task_id,
        post_id=post_id,
        board=board,
        url=url,
        author=_author_id(meta.get("作者")),
        title=meta.get("標題"),
        content=_parse_content(main),
        created_at=created_at,
        crawled_at=crawled_at,
        push_count=counts[CommentType.PUSH],
        boo_count=counts[CommentType.BOO],
        comments=comments,
    )


def post_id_from_url(url: str) -> str:
    """https://www.ptt.cc/bbs/Stock/M.1759730000.A.1B2.html → Stock.M.1759730000.A.1B2。"""
    match = _POST_PATH_RE.fullmatch(urlparse(url).path)
    if not match:
        raise ParseError(f"not a PTT post url: {url!r}")
    return make_post_id(match.group(1), match.group(2))


def _parse_list_entry(node: LexborNode) -> ListEntry:
    nrec = node.css_first("div.nrec")
    link = node.css_first("div.title a")
    title_node = node.css_first("div.title")
    author_node = node.css_first("div.author")
    author = author_node.text(strip=True) if author_node else ""
    url = urljoin(PTT_BASE_URL, link.attributes["href"] or "") if link else None
    return ListEntry(
        post_id=post_id_from_url(url) if url else None,
        url=url,
        title=(link or title_node).text(strip=True) if (link or title_node) else "",
        # NOTE: 被刪除的文章作者欄顯示 "-"
        author=author if author and author != "-" else None,
        list_push=parse_list_push(nrec.text() if nrec else ""),
        is_deleted=link is None,
    )


def _prev_page_url(tree: LexborHTMLParser) -> str | None:
    for link in tree.css("div.btn-group-paging a"):
        href = link.attributes.get("href")
        if "上頁" in link.text() and href:
            return urljoin(PTT_BASE_URL, href)
    return None


def _parse_meta(main: LexborNode) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in main.css("div.article-metaline, div.article-metaline-right"):
        tag = line.css_first("span.article-meta-tag")
        value = line.css_first("span.article-meta-value")
        if tag and value:
            meta[tag.text(strip=True)] = value.text(strip=True)
    return meta


def _author_id(raw: str | None) -> str | None:
    """「zzahoward (Cheshire Cat)」只取帳號。"""
    return raw.split(" (", 1)[0].strip() or None if raw else None


def _parse_content(main: LexborNode) -> str:
    """標頭與推文以外的文字，截到「※ 發信站」，並去掉最後的簽名檔。"""
    parts: list[str] = []
    for node in main.iter(include_text=True):
        if node.is_text_node:
            parts.append(node.text_content or "")
            continue
        classes = _classes(node)
        if classes & {"article-metaline", "article-metaline-right", "push"}:
            continue
        text = node.text()
        if text.startswith(_FOOTER_MARK):
            break
        parts.append(text)
    body = "".join(parts)
    if _SIGNATURE_SEP in body:
        body = body.rsplit(_SIGNATURE_SEP, 1)[0]
    return body.strip()


def _parse_comments(main: LexborNode, post_created_at: datetime) -> list[RawComment]:
    """div.push 依出現順序編 floor（從 1 開始）；警告訊息等非推文的 div.push 略過。"""
    comments: list[RawComment] = []
    for node in main.css("div.push"):
        tag = node.css_first("span.push-tag")
        if tag is None:
            continue
        type_text = tag.text(strip=True)
        if type_text not in _COMMENT_TYPES:
            raise ParseError(f"unknown comment type: {type_text!r}")
        user = node.css_first("span.push-userid")
        content = node.css_first("span.push-content")
        when = node.css_first("span.push-ipdatetime")
        comments.append(
            RawComment(
                floor=len(comments) + 1,
                type=_COMMENT_TYPES[type_text],
                user_id=user.text(strip=True) or None if user else None,
                content=content.text().removeprefix(":").strip() if content else None,
                commented_at=parse_comment_time(when.text(), post_created_at) if when else None,
            )
        )
    return comments


def _classes(node: LexborNode) -> set[str]:
    return set((node.attributes.get("class") or "").split())
