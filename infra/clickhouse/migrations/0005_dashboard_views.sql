-- 開發規格 7.25：dashboard 面板與驗收測試共用的兩個一般 view（不是 materialized）
-- NOTE: 邏輯與 bot/stats.py 的 POST_STATS_QUERY 相同，view 在每次查詢時才計算

CREATE VIEW IF NOT EXISTS post_votes AS
SELECT
    post_id,
    board,
    countIf(type = 'push') AS push,
    countIf(type = 'boo') AS boo,
    countIf(type = 'arrow') AS arrow
FROM comments_latest FINAL
WHERE is_deleted = 0
GROUP BY post_id, board;

CREATE VIEW IF NOT EXISTS post_sentiment_latest AS
SELECT
    post_id,
    argMax(model_version, predicted_at) AS model_version,
    argMax(polarity, predicted_at) AS polarity,
    argMax(arrayMax(mapValues(scores)), predicted_at) AS score
FROM predictions
GROUP BY post_id;
