"""[一次性] 補上 0004 之前推論結果的 text_hash（開發規格 7.19，#37）。

每篇只補 predicted_at 最新的一筆，用 PG posts 目前的標題與內文算 hash；可重跑。
用法：python -m radar.ml.inference.backfill_hash --model models/<model_version>
"""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, select

from radar.common.clickhouse import ClickHouseClient
from radar.common.db.models import Post
from radar.common.db.session import make_engine
from radar.common.ids import split_post_id
from radar.common.log import log, setup_logging
from radar.common.settings import ClickHouseSettings, get_postgres_settings
from radar.ml.inference.main import text_hash
from radar.ml.training.dataset import post_text
from radar.ml.training.train import load_model

# 每篇最新且還沒有 hash 的一筆；時間轉成字串當作更新時的比對鍵
# NOTE: 別名不可叫 predicted_at，否則 HAVING 的 argMax 會引用到 max(...)，變成巢狀聚合
MISSING_QUERY = """
SELECT post_id, toString(max(predicted_at)) AS latest_at
FROM predictions
WHERE model_version = {model_version:String}
GROUP BY post_id
HAVING argMax(text_hash, predicted_at) = ''
"""
PG_BATCH = 1000
# 內嵌進 SQL 的值只允許這些字元（post_id 由 split_post_id 驗證）；時間為 toString(DateTime64(6))
_PREDICTED_AT = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}$")
_MODEL_VERSION = re.compile(r"^[A-Za-z0-9._-]+$")
_HASH = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class MissingHash:
    post_id: str
    predicted_at: str


@dataclass(frozen=True)
class HashUpdate:
    post_id: str
    predicted_at: str
    text_hash: str


def fetch_missing(client: ClickHouseClient, model_version: str) -> list[MissingHash]:
    rows = client.query_rows(MISSING_QUERY, {"model_version": model_version})
    return [MissingHash(str(r["post_id"]), str(r["latest_at"])) for r in rows]


def fetch_texts(engine: Engine, post_ids: list[str], max_chars: int) -> dict[str, str]:
    """post_id → 模型輸入文字（post_text）；PG 沒有或已刪除的不回傳。"""
    texts: dict[str, str] = {}
    with engine.connect() as conn:
        for i in range(0, len(post_ids), PG_BATCH):
            stmt = select(Post.post_id, Post.title, Post.content).where(
                Post.post_id.in_(post_ids[i : i + PG_BATCH]), Post.is_deleted.is_(False)
            )
            for post_id, title, content in conn.execute(stmt):
                texts[post_id] = post_text(title, content, max_chars)
    return texts


def build_updates(missing: list[MissingHash], texts: dict[str, str]) -> list[HashUpdate]:
    """純函式：有文字的才產生更新，hash 與推論服務相同（text_hash）。"""
    return [
        HashUpdate(m.post_id, m.predicted_at, text_hash(texts[m.post_id]))
        for m in missing
        if m.post_id in texts
    ]


def update_statement(model_version: str, updates: list[HashUpdate]) -> str:
    """一批更新組成一個 ALTER TABLE ... UPDATE；只改 text_hash 為空的列，重跑不會覆蓋。"""
    # NOTE: 陣列太大放不進 URL 參數，改成內嵌字面值；post_id、時間、hash 先驗證字元再組 SQL
    if not updates:
        raise ValueError("no updates")
    _check(_MODEL_VERSION, model_version, "model_version")
    keys: list[str] = []
    hashes: list[str] = []
    for u in updates:
        split_post_id(u.post_id)
        _check(_PREDICTED_AT, u.predicted_at, "predicted_at")
        _check(_HASH, u.text_hash, "text_hash")
        keys.append(f"'{u.post_id}|{u.predicted_at}'")
        hashes.append(f"'{u.text_hash}'")
    key = "concat(post_id, '|', toString(predicted_at))"
    return (
        f"ALTER TABLE predictions UPDATE text_hash = "
        f"transform({key}, [{', '.join(keys)}], [{', '.join(hashes)}], text_hash) "
        f"WHERE model_version = '{model_version}' AND text_hash = '' "
        f"AND has([{', '.join(keys)}], {key}) "
        f"SETTINGS mutations_sync = 2"
    )


def _check(pattern: re.Pattern[str], value: str, name: str) -> None:
    if not pattern.match(value):
        raise ValueError(f"invalid {name}: {value!r}")


def apply_updates(
    client: ClickHouseClient, model_version: str, updates: list[HashUpdate], batch_size: int
) -> int:
    """分批執行 update_statement，等每個 mutation 完成；回傳更新的篇數。"""
    # NOTE: 失敗直接往上拋；已完成的批次 text_hash 不再是空字串，重跑時會被略過
    for i in range(0, len(updates), batch_size):
        batch = updates[i : i + batch_size]
        client.execute(update_statement(model_version, batch))
        log.info("updated %d / %d", min(i + batch_size, len(updates)), len(updates))
    return len(updates)


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("backfill-hash")
    parser = argparse.ArgumentParser(description="補上舊推論結果的 text_hash（#37）")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true", help="只統計要補的篇數，不寫入")
    args = parser.parse_args()
    _, card = load_model(args.model)
    ch = ClickHouseClient(ClickHouseSettings())
    engine = make_engine(get_postgres_settings(), pool_size=1)
    try:
        missing = fetch_missing(ch, card.model_version)
        texts = fetch_texts(engine, [m.post_id for m in missing], card.max_chars)
        updates = build_updates(missing, texts)
        log.info(
            "%s: %d posts without hash, %d found in PG",
            card.model_version,
            len(missing),
            len(updates),
        )
        if args.dry_run or not updates:
            return
        apply_updates(ch, card.model_version, updates, args.batch_size)
    finally:
        ch.close()
        engine.dispose()


if __name__ == "__main__":
    main()
