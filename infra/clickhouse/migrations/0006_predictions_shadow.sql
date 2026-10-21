-- 開發規格 7.27（階段 8）：shadow 推論的結果，結構同 predictions（含 text_hash，見 0004）
-- NOTE: 與 predictions 分開：呈現層取「每篇最新一筆」時不分版本，混在一起會改變使用者看到的情緒

CREATE TABLE IF NOT EXISTS predictions_shadow
(
    post_id       String,
    model_version LowCardinality(String),
    predicted_at  DateTime64(6, 'UTC'),
    polarity      LowCardinality(String),
    scores        Map(String, Float64),
    text_hash     String DEFAULT ''
)
ENGINE = MergeTree
ORDER BY (post_id, model_version, predicted_at);

CREATE TABLE IF NOT EXISTS predictions_shadow_queue
(
    post_id       String,
    model_version String,
    predicted_at  String,
    polarity      String,
    scores        Map(String, Float64),
    text_hash     String
)
ENGINE = Kafka(json_kafka, kafka_topic_list = 'predictions.shadow', kafka_group_name = 'clickhouse-predictions-shadow');

CREATE MATERIALIZED VIEW IF NOT EXISTS predictions_shadow_mv TO predictions_shadow AS
SELECT
    post_id, model_version,
    parseDateTime64BestEffort(predicted_at, 6, 'UTC') AS predicted_at,
    polarity, scores, text_hash
FROM predictions_shadow_queue;
