"""假 PTT 伺服器（開發規格 5、S1-07）：產生與 PTT 相同結構的頁面，並能動態增加推文。

只給端到端測試使用；compose 以掛載 tests/ 的方式啟動：uvicorn tests.e2e.fake_ptt:app
"""

import html
import itertools
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

PTT_TZ = ZoneInfo("Asia/Taipei")
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# PTT 實際的推文標籤樣式（噓、→ 為紅色 f1）
_TAGS = {
    "推": '<span class="hl push-tag">推 </span>',
    "噓": '<span class="f1 hl push-tag">噓 </span>',
    "→": '<span class="f1 hl push-tag">→ </span>',
}


@dataclass
class FakeComment:
    type: str  # 推 / 噓 / →
    user_id: str
    content: str
    time_text: str  # "10/07 12:35"


@dataclass
class FakePost:
    board: str
    filename: str  # M.<epoch>.A.<hex>
    title: str
    author: str
    content: str
    created_at: datetime
    comments: list[FakeComment] = field(default_factory=list)
    deleted: bool = False

    @property
    def post_id(self) -> str:
        return f"{self.board}.{self.filename}"

    @property
    def path(self) -> str:
        return f"/bbs/{self.board}/{self.filename}.html"

    def list_push(self) -> str:
        """列表頁推文數欄位，規則同 PTT：推減噓，>= 100 顯示爆，<= -10 顯示 X。"""
        pushes = sum(c.type == "推" for c in self.comments)
        score = pushes - sum(c.type == "噓" for c in self.comments)
        if score >= 100:
            return "爆"
        if score <= -100:
            return "XX"
        if score <= -10:
            return f"X{-score // 10}"
        return str(score) if score > 0 else ""


class NewPost(BaseModel):
    board: str
    title: str
    content: str = "測試內文"


class NewComments(BaseModel):
    pushes: int = 0
    boos: int = 0


class FakePtt:
    """記憶體中的看板與文章；控制端點與頁面端點共用。"""

    def __init__(self) -> None:
        self.posts: dict[str, FakePost] = {}
        self._counter = itertools.count(1)
        self._lock = threading.Lock()

    def add_post(self, data: NewPost) -> FakePost:
        with self._lock:
            now = datetime.now(UTC).replace(microsecond=0)
            # epoch + 遞增的 hex，同一秒內建立多篇也不會重複
            filename = f"M.{int(now.timestamp())}.A.{next(self._counter) % 0xFFF:03X}"
            post = FakePost(data.board, filename, data.title, "e2euser", data.content, now)
            self.posts[post.post_id] = post
            return post

    def add_comments(self, post_id: str, data: NewComments) -> FakePost:
        post = self._get(post_id)
        time_text = datetime.now(PTT_TZ).strftime("%m/%d %H:%M")
        with self._lock:
            for type_, count in (("推", data.pushes), ("噓", data.boos)):
                for _ in range(count):
                    n = len(post.comments) + 1
                    post.comments.append(FakeComment(type_, f"user{n}", f"推文{n}", time_text))
        return post

    def delete(self, post_id: str) -> None:
        self._get(post_id).deleted = True

    def reset(self) -> None:
        with self._lock:
            self.posts.clear()

    def render_list(self, board: str) -> str:
        posts = sorted(
            (p for p in self.posts.values() if p.board == board), key=lambda p: p.created_at
        )
        rows = "".join(_list_row(p) for p in posts)
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>看板 {board} 文章列表 - 批踢踢實業坊</title></head>
<body>
<div class="btn-group btn-group-paging">
<a class="btn wide" href="/bbs/{board}/index1.html">最舊</a>
<a class="btn wide disabled">&lsaquo; 上頁</a>
<a class="btn wide disabled">下頁 &rsaquo;</a>
<a class="btn wide" href="/bbs/{board}/index.html">最新</a>
</div>
<div class="r-list-container action-bar-margin bbs-screen">
{rows}
</div>
</body></html>"""

    def render_post(self, board: str, filename: str) -> str | None:
        """不存在或已刪除回傳 None（回 404）。"""
        post = self.posts.get(f"{board}.{filename}")
        if post is None or post.deleted:
            return None
        meta = "".join(
            f'<div class="{cls}"><span class="article-meta-tag">{tag}</span>'
            f'<span class="article-meta-value">{html.escape(value)}</span></div>'
            for cls, tag, value in (
                ("article-metaline", "作者", f"{post.author} (e2e)"),
                ("article-metaline-right", "看板", post.board),
                ("article-metaline", "標題", post.title),
                ("article-metaline", "時間", _article_time(post.created_at)),
            )
        )
        pushes = "".join(
            f'<div class="push">{_TAGS[c.type]}'
            f'<span class="f3 hl push-userid">{c.user_id}</span>'
            f'<span class="f3 push-content">: {html.escape(c.content)}</span>'
            f'<span class="push-ipdatetime"> {c.time_text}\n</span></div>'
            for c in post.comments
        )
        url = f"https://www.ptt.cc{post.path}"
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{html.escape(post.title)} - 看板 {board} - 批踢踢實業坊</title></head>
<body>
<div id="main-content" class="bbs-screen bbs-content">{meta}{html.escape(post.content)}

--
<span class="f2">※ 發信站: 批踢踢實業坊(ptt.cc), 來自: 192.0.2.1 (臺灣)
</span><span class="f2">※ 文章網址: <a href="{url}">{url}</a>
</span>{pushes}</div>
</body></html>"""

    def _get(self, post_id: str) -> FakePost:
        if post_id not in self.posts:
            raise KeyError(post_id)
        return self.posts[post_id]


def _list_row(post: FakePost) -> str:
    if post.deleted:
        title = f"(本文已被刪除) [{post.author}]"
        author = "-"
    else:
        title = f'<a href="{post.path}">{html.escape(post.title)}</a>'
        author = post.author
    push = post.list_push()
    nrec = f'<span class="hl f2">{push}</span>' if push else ""
    date = post.created_at.astimezone(PTT_TZ).strftime("%m/%d").lstrip("0")
    return f"""<div class="r-ent">
<div class="nrec">{nrec}</div>
<div class="title">{title}</div>
<div class="meta">
<div class="author">{author}</div><div class="date">{date}</div><div class="mark"></div>
</div>
</div>
"""


def _article_time(created_at: datetime) -> str:
    """PTT 標頭格式，例："Wed Oct  7 11:51:41 2026"（台北時間）。"""
    t = created_at.astimezone(PTT_TZ)
    return f"{_DAYS[t.weekday()]} {_MONTHS[t.month - 1]} {t.day:>2} {t:%H:%M:%S} {t.year}"


def create_app(state: FakePtt | None = None) -> FastAPI:
    """頁面：/bbs/{board}/index.html、/bbs/{board}/{filename}.html
    控制：POST /_control/posts、POST /_control/posts/{post_id}/comments、
         DELETE /_control/posts/{post_id}、POST /_control/reset
    """
    ptt = state or FakePtt()
    app = FastAPI(title="fake PTT")

    @app.get("/bbs/{board}/{page}", response_class=HTMLResponse)
    def page(board: str, page: str) -> str:
        if page.startswith("index"):
            return ptt.render_list(board)
        body = ptt.render_post(board, page.removesuffix(".html"))
        if body is None:
            raise HTTPException(404)
        return body

    @app.post("/_control/posts")
    def add_post(data: NewPost) -> dict[str, str]:
        post = ptt.add_post(data)
        return {"post_id": post.post_id, "url": f"https://www.ptt.cc{post.path}"}

    @app.post("/_control/posts/{post_id}/comments")
    def add_comments(post_id: str, data: NewComments) -> dict[str, int]:
        try:
            post = ptt.add_comments(post_id, data)
        except KeyError as e:
            raise HTTPException(404) from e
        return {"comments": len(post.comments)}

    @app.delete("/_control/posts/{post_id}", status_code=204)
    def delete_post(post_id: str) -> None:
        try:
            ptt.delete(post_id)
        except KeyError as e:
            raise HTTPException(404) from e

    @app.post("/_control/reset", status_code=204)
    def reset() -> None:
        ptt.reset()

    return app


app = create_app()
