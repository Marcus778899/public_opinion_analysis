"""[本機] 人工標註頁（S3-04）：一篇一頁，鍵盤選情緒，可補對象。

用法：python -m radar.ml.labeling.human_app（http://127.0.0.1:8090）
標註準則見 docs/labeling-guideline.md。
"""

from collections.abc import Callable
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError

from radar.common.clickhouse import ClickHouseClient
from radar.common.log import log, setup_logging
from radar.common.schemas import Sentiment
from radar.common.settings import ClickHouseSettings
from radar.ml.labeling.prompt import PostText
from radar.ml.labeling.sampling import fetch_posts as fetch_from_clickhouse
from radar.ml.labeling.testset import (
    TESTSET_DIR,
    HumanLabel,
    append_human_label,
    load_human_labels,
    load_post_ids,
)

HOST = "127.0.0.1"
PORT = 8090


class Progress(BaseModel):
    labeled: int
    total: int


class PostOut(BaseModel):
    post: PostText
    index: int
    existing: list[Sentiment] | None = None
    note: str | None = None


class NextPost(BaseModel):
    item: PostOut | None
    progress: Progress


class HumanLabelIn(BaseModel):
    post_id: str
    sentiments: list[Sentiment]
    note: str | None = None


def create_app(
    testset_dir: Path,
    fetch_posts: Callable[[list[str]], dict[str, PostText]],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    """fetch_posts 注入，測試時換成 fake，不連 ClickHouse。"""
    app = FastAPI(title="radar human labeling", docs_url=None, redoc_url=None)

    def post_ids() -> list[str]:
        return load_post_ids(testset_dir)

    def item(ids: list[str], index: int) -> PostOut:
        post_id = ids[index]
        post = fetch_posts([post_id]).get(post_id)
        if post is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"post {post_id} not found")
        label = load_human_labels(testset_dir).get(post_id)
        return PostOut(
            post=post,
            index=index,
            existing=label.sentiments if label else None,
            note=label.note if label else None,
        )

    page = files("radar.ml.labeling").joinpath("human_app.html").read_text(encoding="utf-8")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        # NOTE: 單頁、不載入外部資源（標註資料不外流）
        return page

    @app.get("/api/next")
    def next_post() -> NextPost:
        ids = post_ids()
        done = load_human_labels(testset_dir)
        progress = Progress(labeled=sum(pid in done for pid in ids), total=len(ids))
        pending = [i for i, pid in enumerate(ids) if pid not in done]
        return NextPost(item=item(ids, pending[0]) if pending else None, progress=progress)

    @app.get("/api/posts/{index}")
    def post_at(index: int) -> PostOut:
        ids = post_ids()
        if not 0 <= index < len(ids):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "index out of range")
        return item(ids, index)

    @app.post("/api/labels", status_code=status.HTTP_201_CREATED)
    def save(data: HumanLabelIn) -> Progress:
        ids = post_ids()
        if data.post_id not in ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "post is not in the testset")
        try:
            label = HumanLabel(
                post_id=data.post_id, sentiments=data.sentiments, labeled_at=now(), note=data.note
            )
        except ValidationError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        append_human_label(testset_dir, label)
        done = load_human_labels(testset_dir)
        return Progress(labeled=sum(pid in done for pid in ids), total=len(ids))

    return app


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("human-label")
    ch = ClickHouseClient(ClickHouseSettings())
    app = create_app(TESTSET_DIR, lambda ids: fetch_from_clickhouse(ch, ids))
    log.info("open http://%s:%d", HOST, PORT)
    try:
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
    finally:
        ch.close()


if __name__ == "__main__":
    main()
