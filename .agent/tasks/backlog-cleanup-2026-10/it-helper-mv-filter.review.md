APPROVE a1d5810

# Review PR #141（it-helper-mv-filter）

## 檢查項目

| 項目 | 結果 |
|---|---|
| 負責檔案 | PR 只改 `tests/helpers/clickhouse.py`、`tests/unit/helpers/__init__.py`、`tests/unit/helpers/test_clickhouse_helper.py`；沒碰禁區（`src/`、`tools/`、migration、`tests/integration/`） |
| 驗收 1：`without_kafka` | `is_kafka_statement`：`ENGINE = Kafka` 或「`CREATE MATERIALIZED VIEW` 且 `FROM <x>_queue`」。實際載入 5 個 migration 確認：`split_statements` 已去掉 `--` 註解，結果與舊版相同（現有 MV 都讀 `*_queue`）。單元測試涵蓋讀 queue 的 MV 移除、讀一般表的 MV 保留 |
| 驗收 2：`is_current` | 先比對版本集合，再查 `system.tables`（engine 為 Kafka／MaterializedView），確認 `kafka_objects` 是它的子集合；我實跑 `kafka_objects` 得到 11 個（0003 DROP 的 `comments_mv` 已扣掉，0004 重建的 predictions 還在），結果正確。consumer 存活不查 `system.kafka_consumers`（欄位依版本而異），回報有說明，這是驗收條件允許的替代做法。缺表、缺 migration、ClickHouseError 都有單元測試 |
| 安全 | `is_current` 新增的 f-string SQL 只帶入 `settings.db`，而 `assert_test_clickhouse` 已經限定它是 `radar`，與檔內既有寫法一致；沒有新的寫死設定 |
| 失敗方向 | `is_current` 誤判時只會回 False，結果是整套重建（較慢，但安全）；不會在 consumer 缺席時誤回 True，除非物件都還在 |
| 驗證 | CI：Check、Integration Test、Security 都通過。qa 跑了 3 次全新／重用堆疊，都是 329 passed，並已 `down -v` |

## qa 備註：`kafka_objects` 只處理 CREATE／DROP，沒處理 RENAME

判定：現在不用改程式，也不擋這次合併。理由如下：

- 現有 migration 沒有 RENAME、EXCHANGE，也沒有 `ALTER … MODIFY QUERY`。0003、0004 的 NOTE 也寫明，Kafka 物件的慣例是「刪掉重建」或「換新表名」，不用 RENAME
- 就算之後有人用 RENAME，失敗也看得到，不會悄悄出錯：
  - `is_current` 會因為舊名稱不存在而一直回 False，每次都整套重建（約多 45 秒），測試結果仍然正確
  - `without_kafka` 不會濾掉 RENAME，worker DB 裡沒有那張 queue 表，所以 RENAME 會直接報錯，migration 失敗
- 不處理 RENAME 的成本只是測試變慢或明確報錯，沒有資料錯誤的風險，所以不值得為它加解析邏輯

建議（非阻擋，下一張碰到這裡的單順手做；不需要開單）：

1. 在 `tests/helpers/clickhouse.py` 的 `_CREATE_RE` 上方加一行 NOTE：「依賴 Kafka engine 表命名為 `*_queue`，且 Kafka 物件只用 CREATE／DROP 變更；migration 改用 RENAME／EXCHANGE 時要同步改 `kafka_objects`」
2. 開發規格 7.26 實作補充 ④ 有一句「`radar` 已套完所有 migration 時（`is_current`）」，現在 `is_current` 還會另外確認 Kafka engine 表與讀它的 MV 都存在，那句後面應補上這一點，並加上第 1 點的限制。本單的負責檔案不含 docs，所以由 manager 決定交給哪張文件單；這是依 CLAUDE.md「文件同步」要做的，算小幅文件落差
3. `tests/integration/test_parallel_isolation.py::test_without_kafka_removes_engine_tables_and_views_only` 仍斷言 kept 裡沒有任何 `MATERIALIZED VIEW`，與新的語意不一致：現在之所以會過，只是因為目前沒有讀一般表的 MV，等第一個這種 MV 出現就會誤報失敗。它在本單禁區（`tests/integration/`），所以列為後續；建議改成斷言「沒有 `ENGINE = Kafka`，也沒有讀 `*_queue` 的 MV」，或直接刪掉，因為已經被 `tests/unit/helpers` 的測試取代

## 問題數量

阻擋 0；非阻擋建議 3（見上）
