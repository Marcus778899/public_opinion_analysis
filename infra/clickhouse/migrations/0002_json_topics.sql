-- S2-06：labels、predictions、alerts 的 JSON topic 接入（訊息格式見開發規格 3.4～3.6）
-- NOTE: 時間欄位同 0001，Kafka engine 表收 String、在 MV 轉換；未列出的欄位（例如 schema_version）略過

CREATE TABLE IF NOT EXISTS labels_queue
(
    post_id    String,
    labeler    String,
    version    String,
    labeled_at String,
    sentiments Array(Tuple(target Nullable(String), polarity String))
)
ENGINE = Kafka(json_kafka, kafka_topic_list = 'labels', kafka_group_name = 'clickhouse-labels');

-- 一列一個 (target, polarity)，target 為 NULL 代表整篇（設計文件 15.3）
CREATE TABLE IF NOT EXISTS labels
(
    post_id    String,
    labeler    LowCardinality(String),
    version    LowCardinality(String),
    labeled_at DateTime64(6, 'UTC'),
    target     Nullable(String),
    polarity   LowCardinality(String)
)
ENGINE = MergeTree
ORDER BY (post_id, labeler, version);

CREATE TABLE IF NOT EXISTS predictions_queue
(
    post_id       String,
    model_version String,
    predicted_at  String,
    polarity      String,
    scores        Map(String, Float64)
)
ENGINE = Kafka(json_kafka, kafka_topic_list = 'predictions', kafka_group_name = 'clickhouse-predictions');

CREATE TABLE IF NOT EXISTS predictions
(
    post_id       String,
    model_version LowCardinality(String),
    predicted_at  DateTime64(6, 'UTC'),
    polarity      LowCardinality(String),
    scores        Map(String, Float64)
)
ENGINE = MergeTree
ORDER BY (post_id, model_version, predicted_at);

CREATE TABLE IF NOT EXISTS alerts_queue
(
    alert_id        String,
    unit_type       String,
    unit_key        String,
    board           Nullable(String),
    window_start    String,
    window_end      String,
    value           Float64,
    baseline        Float64,
    zscore          Float64,
    sample_post_ids Array(String),
    created_at      String
)
ENGINE = Kafka(json_kafka, kafka_topic_list = 'alerts', kafka_group_name = 'clickhouse-alerts');

CREATE TABLE IF NOT EXISTS alerts
(
    alert_id        UUID,
    unit_type       LowCardinality(String),
    unit_key        String,
    board           LowCardinality(Nullable(String)),
    window_start    DateTime64(6, 'UTC'),
    window_end      DateTime64(6, 'UTC'),
    value           Float64,
    baseline        Float64,
    zscore          Float64,
    sample_post_ids Array(String),
    created_at      DateTime64(6, 'UTC')
)
ENGINE = MergeTree
ORDER BY (unit_type, unit_key, window_start);

CREATE MATERIALIZED VIEW IF NOT EXISTS labels_mv TO labels AS
SELECT
    post_id, labeler, version,
    parseDateTime64BestEffort(labeled_at, 6, 'UTC') AS labeled_at,
    s.target AS target,
    s.polarity AS polarity
FROM labels_queue
ARRAY JOIN sentiments AS s;

CREATE MATERIALIZED VIEW IF NOT EXISTS predictions_mv TO predictions AS
SELECT
    post_id, model_version,
    parseDateTime64BestEffort(predicted_at, 6, 'UTC') AS predicted_at,
    polarity, scores
FROM predictions_queue;

CREATE MATERIALIZED VIEW IF NOT EXISTS alerts_mv TO alerts AS
SELECT
    toUUID(alert_id) AS alert_id, unit_type, unit_key, board,
    parseDateTime64BestEffort(window_start, 6, 'UTC') AS window_start,
    parseDateTime64BestEffort(window_end, 6, 'UTC') AS window_end,
    value, baseline, zscore, sample_post_ids,
    parseDateTime64BestEffort(created_at, 6, 'UTC') AS created_at
FROM alerts_queue;
