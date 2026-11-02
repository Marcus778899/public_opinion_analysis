PASS 0d62e95

# QA：integration-flaky-tests（PR #138，commit 0d62e95）

## 追加 3 條（review 退回）

| 項目 | 結果 |
|---|---|
| ① `cdc/test_slot.py` 補回 `read_slot` 的 lag 斷言 | OK。`git diff c324a04 0d62e95`：同一連線讀 `read_slot` 前後的 `pg_current_wal_lsn`（wal_before、wal_after），斷言 `wal_before - flushed_after <= consumed.lag_bytes <= wal_after - flushed_after`，並保留 `confirmed_flush_lsn` 前進 > 400_000。無 sleep、retry、xdist_group。 |
| ① 平行穩定 | 上下界都以自己 slot 的位置為基準，其他 worker 的寫入只會同時推高兩個界線。實測：全套 -n 8 連跑 3 次、`tests/integration/cdc tests/integration/db -n 8` 再跑一次、-n 0 全套，test_slot 皆通過。 |
| ① 能抓 lag 計算錯誤 | 靜態推演（qa 不改檔，未做變異實測）：`_SLOT_QUERY` 為 `pg_current_wal_lsn - COALESCE(confirmed_flush_lsn, restart_lsn)`。改用 restart_lsn 時 restart_lsn <= confirmed_flush_lsn，lag 會多出 flush 與 restart 的差，超過上界 `wal_after - flushed_after`；不用 pg_current_wal_lsn 或算反也會落在界外。下界與上界都在 SQL 內被實際執行驗證。 |
| ② 改名 | OK：`test_read_slot_after_consuming_changes_lag_measured_from_confirmed_flush`，與新斷言相符。 |
| ③ 開發規格舊句 | OK：7.26 實作補充②舊句後加「（已由 `integration-flaky-tests` 取代，見下方偶發失敗修正）」，新條目③也補述 lag 夾在上下界之間。 |

## 其他驗收條件

| 條件 | 結果 |
|---|---|
| 每個 issue 在回報寫出根因與修法 | OK：`reports/integration-flaky-tests.json` open_questions 含 #110 #126 #111 #117 的根因與修法（#126 查出為 create_partitions 回來時 list_topics 仍是舊 metadata）。 |
| 全新堆疊連跑 3 次全過 | OK，見下方輸出 |
| `-n 0` 全過、做完 down -v | OK，已 `down -v` |
| `make check` | OK：1114 passed in 5.83s（本次親自執行） |
| PR CI | `gh pr checks 138`：Check pass、Integration Test pass（2m14s）、Security pass；headRefOid = 0d62e9577d63…，與驗證的 commit 相同 |
| 禁區 | 變更檔（`git diff c324a04~1 HEAD --stat`）7 個，皆在負責檔案內；src、tests/helpers、scripts 未動 |
| 固定 sleep／retry 掩蓋 | `test_topics_apply.py:38` 的 `time.sleep(0.2)` 是既有的 `wait_visible`（有 deadline 的輪詢），非本次新增；新增處都用 `wait_until` fixture（有 deadline）。 |
| `TODO(integration-flaky-tests)` | grep src tests 無結果 |
| 寫死設定值 | 新增部分沒有 port、網址、token |

## 執行輸出（原始，節錄）

環境：`docker compose ls` 顯示另一個測試堆疊 `it-helper-mv-filter`（5 個容器）同時在跑，沒有因資源不足失敗。先 `down -v` 取得全新堆疊。

```
$ docker compose --env-file .env -f .worktrees/integration-flaky-tests/compose.yaml run --rm test   (全新堆疊，第 1 次)
8 workers [329 items]
============================= 329 passed in 49.07s =============================
(第 2 次)
============================= 329 passed in 43.05s =============================
(第 3 次)
============================= 329 passed in 43.06s =============================

$ ... run --rm test pytest tests/integration -n 0 -q
329 passed in 137.51s (0:02:17)

$ ... run --rm test pytest tests/integration/cdc tests/integration/db -n 8 -q
24 passed in 64.63s (0:01:04)

$ make check
============================= 1114 passed in 5.83s =============================

$ ... down -v
（容器、volume、network 全部 Removed）
```

## 問題

無（0 個）。

備註：變異實測（故意改壞 `_SLOT_QUERY` 看測試是否失敗）因 qa 不可改檔未做，以靜態推演為準。
