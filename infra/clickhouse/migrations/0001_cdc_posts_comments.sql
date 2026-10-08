-- S2-05：CDC topic → posts_latest、posts_history、comments（設計文件 6.2、6.3）
-- NOTE: 時間欄位在 Kafka engine 表宣告為 String，Debezium 送的是 ISO 8601 字串

CREATE TABLE IF NOT EXISTS posts_queue
(
    post_id        String,
    board          String,
    author         Nullable(String),
    title          Nullable(String),
    content        Nullable(String),
    url            String,
    push_count     Int32,
    boo_count      Int32,
    created_at     String,
    crawled_at     String,
    is_deleted     Bool,
    __deleted      Nullable(String),
    __op           Nullable(String),
    __source_ts_ms Nullable(Int64),
    __source_lsn   Nullable(Int64)
)
ENGINE = Kafka(cdc_kafka, kafka_topic_list = 'cdc.public.posts', kafka_group_name = 'clickhouse-posts');

CREATE TABLE IF NOT EXISTS posts_latest
(
    post_id    String,
    board      LowCardinality(String),
    author     Nullable(String),
    title      Nullable(String),
    content    Nullable(String),
    url        String,
    push_count Int32,
    boo_count  Int32,
    created_at DateTime64(6, 'UTC'),
    crawled_at DateTime64(6, 'UTC'),
    is_deleted Bool,
    lsn        Int64
)
ENGINE = ReplacingMergeTree(lsn)
ORDER BY post_id;

CREATE TABLE IF NOT EXISTS posts_history
(
    post_id    String,
    board      LowCardinality(String),
    title      Nullable(String),
    push_count Int32,
    boo_count  Int32,
    created_at DateTime64(6, 'UTC'),
    crawled_at DateTime64(6, 'UTC'),
    is_deleted Bool,
    op         LowCardinality(String),
    changed_at DateTime64(3, 'UTC'),
    lsn        Int64
)
ENGINE = MergeTree
ORDER BY (post_id, lsn);

CREATE TABLE IF NOT EXISTS comments_queue
(
    post_id        String,
    floor          Int32,
    type           String,
    user_id        Nullable(String),
    content        Nullable(String),
    commented_at   Nullable(String),
    __deleted      Nullable(String),
    __op           Nullable(String),
    __source_ts_ms Nullable(Int64),
    __source_lsn   Nullable(Int64)
)
ENGINE = Kafka(cdc_kafka, kafka_topic_list = 'cdc.public.comments', kafka_group_name = 'clickhouse-comments');

CREATE TABLE IF NOT EXISTS comments
(
    post_id      String,
    board        LowCardinality(String),
    floor        Int32,
    type         LowCardinality(String),
    user_id      Nullable(String),
    content      Nullable(String),
    commented_at Nullable(DateTime64(6, 'UTC')),
    changed_at   DateTime64(3, 'UTC'),
    lsn          Int64
)
ENGINE = MergeTree
ORDER BY (post_id, floor);

-- NOTE: MV 建立後立刻開始消費，所以放在目標表之後
CREATE MATERIALIZED VIEW IF NOT EXISTS posts_latest_mv TO posts_latest AS
SELECT
    post_id, board, author, title, content, url, push_count, boo_count,
    parseDateTime64BestEffort(created_at, 6, 'UTC') AS created_at,
    parseDateTime64BestEffort(crawled_at, 6, 'UTC') AS crawled_at,
    is_deleted,
    ifNull(__source_lsn, 0) AS lsn
FROM posts_queue;

CREATE MATERIALIZED VIEW IF NOT EXISTS posts_history_mv TO posts_history AS
SELECT
    post_id, board, title, push_count, boo_count,
    parseDateTime64BestEffort(created_at, 6, 'UTC') AS created_at,
    parseDateTime64BestEffort(crawled_at, 6, 'UTC') AS crawled_at,
    is_deleted,
    ifNull(__op, '') AS op,
    fromUnixTimestamp64Milli(ifNull(__source_ts_ms, 0)) AS changed_at,
    ifNull(__source_lsn, 0) AS lsn
FROM posts_queue;

CREATE MATERIALIZED VIEW IF NOT EXISTS comments_mv TO comments AS
SELECT
    post_id,
    splitByChar('.', post_id)[1] AS board,
    floor, type, user_id, content,
    parseDateTime64BestEffortOrNull(commented_at, 6, 'UTC') AS commented_at,
    fromUnixTimestamp64Milli(ifNull(__source_ts_ms, 0)) AS changed_at,
    ifNull(__source_lsn, 0) AS lsn
FROM comments_queue;
