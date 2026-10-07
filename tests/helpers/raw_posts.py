"""測試用的 RawPost 產生器，單元測試與整合測試共用。"""

import uuid
from datetime import UTC, datetime, timedelta

from radar.common.enums import CommentType
from radar.common.schemas import RawComment, RawPost

T0 = datetime(2026, 10, 7, 4, 0, tzinfo=UTC)


def make_comments(n_push: int = 1, n_boo: int = 0, n_arrow: int = 0) -> list[RawComment]:
    types = [CommentType.PUSH] * n_push + [CommentType.BOO] * n_boo + [CommentType.ARROW] * n_arrow
    return [
        RawComment(floor=i, type=t, user_id=f"u{i}", content=f"c{i}", commented_at=T0)
        for i, t in enumerate(types, 1)
    ]


def make_post(
    post_id: str = "Stock.M.1791345103.A.E41",
    *,
    crawled_at: datetime = T0,
    n_push: int = 1,
    n_boo: int = 0,
    n_arrow: int = 0,
    title: str = "[新聞] 測試",
    content: str = "內文",
    is_deleted: bool = False,
) -> RawPost:
    board = post_id.split(".", 1)[0]
    comments = [] if is_deleted else make_comments(n_push, n_boo, n_arrow)
    return RawPost(
        task_id=uuid.uuid4(),
        post_id=post_id,
        board=board,
        url=f"https://www.ptt.cc/bbs/{board}/{post_id.split('.', 1)[1]}.html",
        author=None if is_deleted else "author1",
        title=None if is_deleted else title,
        content=None if is_deleted else content,
        created_at=T0 - timedelta(hours=1),
        crawled_at=crawled_at,
        push_count=0 if is_deleted else n_push,
        boo_count=0 if is_deleted else n_boo,
        is_deleted=is_deleted,
        comments=comments,
    )
