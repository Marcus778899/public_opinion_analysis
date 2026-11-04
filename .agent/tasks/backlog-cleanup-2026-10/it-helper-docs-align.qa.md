PASS 199cbe9

# 驗證證據 it-helper-docs-align（PR #148，commit 199cbe9）

## 驗收條件
- without_kafka 斷言：diff 移除「不含任何 MATERIALIZED VIEW」，改為「無 `ENGINE = Kafka`」＋「無 `is_kafka_statement` 為真的語句」，保留 labels 表存在斷言。第一條斷言獨立於 helper，沒有退化成同義反覆；helper 若完全不略過，兩條都會失敗。PASS
- test_topics_apply：以 `wait_until` 條件式等待 partitions 與 `retention.ms` 都是新值後才斷言，最終斷言未改、無固定 sleep。PASS（根因為 alter 回來時 metadata／describe_configs 仍是舊值，同 #126；偶發問題本機無法證明根除，CI 與兩次整合測試皆過）
- helper NOTE（只加 2 行註解，無行為變更）、開發規格 7.26 ④（is_current 另查 Kafka 物件、`*_queue` 命名、只用 CREATE／DROP）、`test_slot.py` 的 `conn: Connection` 標註：與實作一致。PASS
- `grep TODO(it-helper-docs-align) src tests`：無結果。
- 跑前 `docker compose ls`：無任何堆疊。
- `make check`：`1152 passed in 3.27s`。
- 整合測試（全新堆疊，同一堆疊連跑 2 次）：第 1 次 `330 passed in 39.63s`，第 2 次 `330 passed in 38.94s`；已 `down -v`（容器、網路、volume 全移除）。
- CI（run 39592592656，head 199cbe9）：Check pass 45s、Security pass 25s、Integration Test pass 2m21s。

## 其他檢查
- diff 只動負責檔案；未改 src／tools／scripts／contracts。
- 無新寫死的設定值。
- 殘留觀察（非阻擋）：`_FROM_QUEUE_RE` 只匹配 `FROM <name>_queue`，不含 `FROM db.name_queue`；屬既有行為，不在此單範圍。

## 問題數量：0
