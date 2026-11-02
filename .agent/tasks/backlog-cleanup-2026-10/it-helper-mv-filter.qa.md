PASS a1d5810

# QA it-helper-mv-filter

## 驗收條件
1. without_kafka：以真實 migration 比對舊版（字串 "ENGINE = Kafka"/"CREATE MATERIALIZED VIEW"）與新版輸出，`old == new` 為 True（5 個 migration）。`kafka_objects` 結果為 11 個物件（posts/comments/labels/predictions/alerts 的 queue 與各 MV），0001 的 `comments_mv` 被 0003 DROP 後正確排除，predictions 被 0004 重建後仍在。單元測試涵蓋「讀 *_queue 的 MV 移除、讀一般表的 MV 保留」與真實 migration。PASS
2. is_current：先比對版本集合（不符回 False），再查 system.tables 內 Kafka／MaterializedView 物件是否涵蓋 kafka_objects；缺 Kafka 表、缺 migration、ClickHouseError 皆回 False，全齊回 True（單元 4 例）。DB 已是最新時回 True，故不會誤判重建（連續第 2、3 次在同一堆疊執行整套全過，走的就是 is_current True 路徑）。consumer 狀態：不查 system.kafka_consumers（版本相依），只查物件存在；說明合理，驗收條件本就允許「說明為何不可行與替代做法」。PASS
3. 整合測試全套（先 `docker compose ls` 確認無其他堆疊，全新堆疊）：
   - 第 1 次 `329 passed in 49.82s`
   - 第 2 次（重用堆疊）`329 passed in 42.47s`
   - 第 3 次 `329 passed in 40.49s`
   dashboard test_panels 三輪皆過，未重現 min_score 失敗，與 worker 判斷（環境／偶發，OOM 與雙堆疊同時運作有關）一致。已 `down -v`，容器、volume、network 全移除。PASS
4. 本機 `uv run pytest tests/unit` 1128 passed；`ruff check` 全過、`ruff format --check` 257 files already formatted；`grep TODO(it-helper-mv-filter) src tests` 無結果。CI 狀態未在本次驗證（沒有 gh 查詢），請 manager 於 PR #141 確認。PASS（CI 除外）

## 其他檢查
- 只改負責檔案（tests/helpers/clickhouse.py、tests/unit/helpers/*）；diff 內 BOARD.md 的差異來自主目錄未提交變更，非 worker 改動。
- 無寫死 port／網址／機密新增（既有測試專用帳密有 NOTE 註解）。
- 邊界：_CREATE_RE／_DROP_RE 只比對語句開頭，ALTER／RENAME 目前 migration 沒有；之後若 migration 用 RENAME 改 Kafka 表，kafka_objects 會失準（非阻擋，現有 migration 無此情形）。

問題數量：0
