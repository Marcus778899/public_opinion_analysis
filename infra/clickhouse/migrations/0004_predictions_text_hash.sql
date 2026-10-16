-- 開發規格 7.19（#37）：predictions 新增 text_hash，推論服務重啟時用來重建快取
-- NOTE: Kafka engine 表不能 ALTER 加欄位，queue 與 MV 刪掉重建；consumer group 不變，
-- offset 存在 Kafka，重建期間送來的訊息留在 topic，不會遺失也不會重複

DROP VIEW IF EXISTS predictions_mv;

DROP TABLE IF EXISTS predictions_queue;

ALTER TABLE predictions ADD COLUMN IF NOT EXISTS text_hash String DEFAULT '';

-- 舊訊息沒有 text_hash：JSONEachRow 以型別預設值（空字串）代入；Kafka engine 不支援 DEFAULT
CREATE TABLE IF NOT EXISTS predictions_queue
(
    post_id       String,
    model_version String,
    predicted_at  String,
    polarity      String,
    scores        Map(String, Float64),
    text_hash     String
)
ENGINE = Kafka(json_kafka, kafka_topic_list = 'predictions', kafka_group_name = 'clickhouse-predictions');

CREATE MATERIALIZED VIEW IF NOT EXISTS predictions_mv TO predictions AS
SELECT
    post_id, model_version,
    parseDateTime64BestEffort(predicted_at, 6, 'UTC') AS predicted_at,
    polarity, scores, text_hash
FROM predictions_queue;
