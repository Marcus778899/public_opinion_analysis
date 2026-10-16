-- 開發規格 7.15：推文會被改寫、刪除，comments 改成以 LSN 取代的 comments_latest
-- NOTE: ClickHouse 不能改 engine，EXCHANGE TABLES 重跑又會換回來，所以用新表名；
-- 複製資料那一步重跑時舊表可能已刪，失敗需手動處理

CREATE TABLE IF NOT EXISTS comments_latest
(
    post_id      String,
    board        LowCardinality(String),
    floor        Int32,
    type         LowCardinality(String),
    user_id      Nullable(String),
    content      Nullable(String),
    commented_at Nullable(DateTime64(6, 'UTC')),
    changed_at   DateTime64(3, 'UTC'),
    lsn          Int64,
    is_deleted   UInt8
)
ENGINE = ReplacingMergeTree(lsn, is_deleted)
ORDER BY (post_id, floor);

-- NOTE: 先停舊 MV；沒有 MV 時 Kafka engine 表不消費，offset 不動，不會漏訊息
DROP VIEW IF EXISTS comments_mv;

INSERT INTO comments_latest
SELECT post_id, board, floor, type, user_id, content, commented_at, changed_at, lsn, 0
FROM comments;

CREATE MATERIALIZED VIEW IF NOT EXISTS comments_latest_mv TO comments_latest AS
SELECT
    post_id,
    splitByChar('.', post_id)[1] AS board,
    floor, type, user_id, content,
    parseDateTime64BestEffortOrNull(commented_at, 6, 'UTC') AS commented_at,
    fromUnixTimestamp64Milli(ifNull(__source_ts_ms, 0)) AS changed_at,
    ifNull(__source_lsn, 0) AS lsn,
    toUInt8(ifNull(__deleted, 'false') = 'true') AS is_deleted
FROM comments_queue;

DROP TABLE IF EXISTS comments;
