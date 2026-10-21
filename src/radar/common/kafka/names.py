"""topics.yaml 管理的 topic 名稱；需與 infra/kafka/topics.yaml 一致（由單元測試檢查）。"""

CRAWL_TASKS = "crawl.tasks"
RAW_POSTS = "raw.posts"
RAW_HTML = "raw.html"
CDC_POSTS = "cdc.public.posts"
CDC_COMMENTS = "cdc.public.comments"
LABELS = "labels"
PREDICTIONS = "predictions"
# shadow 推論的輸出，與 predictions 分開，呈現層不受影響（開發規格 7.27）
PREDICTIONS_SHADOW = "predictions.shadow"
ALERTS = "alerts"
# 熱度偵測的回放與人工暴增（開發規格 7.20）
REPLAY_COMMENTS = "replay.cdc.comments"
DLQ = "dlq"
CDC_HEARTBEAT = "__debezium-heartbeat.cdc"
