APPROVE 3a7f5c0

# Code review scheduler-statement-timeout（PR #239，對 develop）

## 檢查項目

| 項目 | 結果 | 說明 |
|---|---|---|
| 負責檔案 | OK | 10 個檔案都在派工單（含追加）的負責檔案內；驗收測試只有 qa 的 85b9304 `test(...)` 動過，worker commit 3a7f5c0 沒改 |
| 介面照鎖定的驗收測試 | OK | `SCHEDULER_STATEMENT_TIMEOUT_SEC` → `SchedulerSettings.statement_timeout_sec`（預設 30.0）；`make_engine(..., statement_timeout_sec=None)` |
| 其他服務行為不變 | OK | `make_engine` 不傳參數時 kwargs 與原本相同（`pool_size`、`pool_pre_ping`），沒有 `connect_args`；只有 `scheduler.main()` 傳新參數 |
| 只有逾時略過該輪 | OK | `is_query_timeout()` 只認 `DBAPIError.orig` 為 `psycopg.errors.QueryCanceled`；`latest_post_since` 其他錯誤照舊回 None，逾時往上拋，`send_list_task` 記 WARNING 後 return（不送任務）；`DuePostDispatcher` 只包 `find_due_posts`，非逾時照拋 |
| 失敗 transaction 收尾 | OK | dispatcher 逾時後 `return 0` 離開 `with session`，session close 時 rollback，連線回 pool 不帶壞狀態 |
| 設定、文件 | OK | 沒有寫死值；`.env.example` 依 D-009 寫成註解；開發規格 7.28 A 加「查詢逾時」列，與實作一致 |
| 測試 | OK | 驗收測試涵蓋：預設與環境變數、毫秒換算、預設行為不變、main 有傳值、兩個 fail 點的略過＋WARNING、下一輪恢復、單一看板逾時不中止、dispatcher 略過與非逾時照拋；單元測試補 `is_query_timeout` 真偽與小數秒換算。qa 另以真實 PG 驗證 `QueryCanceled` 確實包成 `OperationalError` |
| 驗證 | 已跑 | worktree 內 `uv run pytest tests/unit/acceptance/scheduler-statement-timeout tests/unit/collector tests/unit/common -q` → `427 passed in 1.56s` |

## qa 三項觀察的判斷（都不要求這張單修改）

| 觀察 | 判斷 | 理由 |
|---|---|---|
| 1. 逾時秒數沒有範圍驗證 | 不改 | 0 是 PG 的「不逾時」，合法；負值會讓第一次連線（`AdvisoryLock.try_acquire`，啟動時）就失敗，`main()` 的 `log.catch` 記 CRITICAL 後結束，已是 fail fast，只是錯誤訊息不直白。小於 0.0005 秒會被 round 成 0（等於關掉），屬極端設定錯誤。若要加 `Field(ge=0)` 可另開 backlog，不阻擋 |
| 2. `record_dispatch`／commit 逾時往上拋 | 不改 | 派工單追加只要求「查詢逾時略過」；寫入逾時由 `_logged` 記錄、下一輪重試，開發規格已載明重複派發無害。結果等同略過該輪，差別只在記 ERROR 而非 WARNING |
| 3. advisory lock 共用 engine | 不改，但記下影響 | `pg_try_advisory_lock`、`pg_locks` 查詢不會被鎖擋住；唯一影響是 PG 嚴重過載使 `is_held()` 超過 30 秒時會被取消 → 回 False → 心跳判定失鎖、scheduler 停止，交給容器重啟。改動前同情境是無限卡住，這是改善，不是退步 |

## 問題

無。
