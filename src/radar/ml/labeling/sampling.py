"""從 ClickHouse 依看板分層抽樣（開發規格 7.11）；同一個 seed 重跑結果一致。"""

from dataclasses import dataclass

from radar.common.clickhouse import ClickHouseClient
from radar.ml.labeling.prompt import PostText


@dataclass(frozen=True)
class SampleSpec:
    per_board: int
    seed: int
    boards: list[str] | None = None
    # 續跑用：排除已有這組 labeler + version 標註的文章
    skip_labeler: str | None = None
    skip_version: str | None = None
    # 內文太短（只有連結或一兩個字）沒有可判斷的情緒
    min_chars: int = 20
    # 為了排除人工測試集而多抓的篇數，每個看板各加這麼多
    extra_per_board: int = 0


def array_param(values: list[str]) -> str:
    """ClickHouse HTTP 參數的 Array(String) 寫法。"""
    escaped = [v.replace("\\", "\\\\").replace("'", "\\'") for v in values]
    return "[" + ",".join(f"'{v}'" for v in escaped) + "]"


def build_sample_query(spec: SampleSpec) -> tuple[str, dict[str, str]]:
    """回傳 (SQL, params)；SQL 只用 {name:Type} 參數，不拼接值。"""
    where = ["NOT is_deleted", "length(ifNull(content, '')) >= {min_chars:UInt32}"]
    params = {
        "seed": str(spec.seed),
        "limit": str(spec.per_board + spec.extra_per_board),
        "min_chars": str(spec.min_chars),
    }
    if spec.boards:
        where.append("board IN {boards:Array(String)}")
        params["boards"] = array_param(spec.boards)
    if spec.skip_labeler and spec.skip_version:
        where.append(
            "post_id NOT IN (SELECT post_id FROM labels "
            "WHERE labeler = {skip_labeler:String} AND version = {skip_version:String})"
        )
        params["skip_labeler"] = spec.skip_labeler
        params["skip_version"] = spec.skip_version
    sql = (
        "SELECT post_id, board, title, content FROM posts_latest FINAL\n"
        f"WHERE {' AND '.join(where)}\n"
        "ORDER BY board, cityHash64(post_id, {seed:UInt64})\n"
        "LIMIT {limit:UInt32} BY board"
    )
    return sql, params


def _to_post(row: dict[str, str]) -> PostText:
    return PostText(
        post_id=row["post_id"],
        board=row["board"],
        title=row.get("title"),
        content=row.get("content"),
    )


def sample_posts(
    client: ClickHouseClient, spec: SampleSpec, exclude_ids: set[str]
) -> list[PostText]:
    sql, params = build_sample_query(spec)
    taken: dict[str, int] = {}
    posts: list[PostText] = []
    for row in client.query_rows(sql, params):
        if row["post_id"] in exclude_ids or taken.get(row["board"], 0) >= spec.per_board:
            continue
        taken[row["board"]] = taken.get(row["board"], 0) + 1
        posts.append(_to_post(row))
    return posts


def fetch_posts(client: ClickHouseClient, post_ids: list[str]) -> dict[str, PostText]:
    if not post_ids:
        return {}
    rows = client.query_rows(
        "SELECT post_id, board, title, content FROM posts_latest FINAL "
        "WHERE post_id IN {ids:Array(String)}",
        {"ids": array_param(post_ids)},
    )
    return {r["post_id"]: _to_post(r) for r in rows}


def labeled_post_ids(
    client: ClickHouseClient, labeler: str, version: str, post_ids: list[str]
) -> set[str]:
    """post_ids 中已有這組 labeler + version 標註的文章（續跑用）。"""
    if not post_ids:
        return set()
    rows = client.query_rows(
        "SELECT DISTINCT post_id FROM labels\n"
        "WHERE labeler = {labeler:String} AND version = {version:String}\n"
        "  AND post_id IN {ids:Array(String)}",
        {"labeler": labeler, "version": version, "ids": array_param(post_ids)},
    )
    return {r["post_id"] for r in rows}
