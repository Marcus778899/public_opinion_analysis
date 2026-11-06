PASS 1555183

# QA consumer-commit-wait（PR #210）

## 驗收條件
1. 等待中途 stop：驗收測試 `test_stop_during_commit_wait_ends_within_one_segment_without_commit` 通過（fake sleep/clock，每段 <= 0.5，commits == 0，已 close，不拋出，停止後不再多睡）。
2. `grep -rn "_stop.wait" src/radar`：無結果（實跑）。
3. `grep -rn "TODO(consumer-commit-wait)" src tests`：無結果。

## 實跑輸出
- `uv run pytest tests/unit/acceptance/consumer-commit-wait tests/unit/common` -> `250 passed in 0.90s`
- `uv run pytest tests/unit` -> `1420 passed in 14.11s`
- `uv run ruff check .` -> All checks passed；`ruff format --check .` -> 295 files already formatted
- `pre-commit run --all-files`（make check 的第一步）-> 全部 Passed（trailing whitespace、end of files、yaml、ruff、ruff format、bandit）

## 既有測試改寫檢查
`test_stop_during_commit_retry_wait_leaves_batch_uncommitted` 原本用 `StopOnWait` 覆寫 `Event.wait`，現在 `Event.wait` 已不使用，改成注入 `_sleep`，在 sleep 時呼叫 `stop()`，backoff 設 5.0 秒。斷言仍是 `commits == 0` 且 `closed`。
停止後必須不再重試 commit 才能通過：commit_errors 只有一筆，若重試會成功而 commits == 1。所以測試仍驗到原行為（等待中收到 stop，批次不 commit）。

## 其他檢查
- 新增 `sleep` 建構參數預設 `time.sleep`，預設行為不變；重試次數與退避策略未動（符合禁區）。
- 無寫死的設定值。0 秒延遲、停止前已設定、不使用 Event.wait 的邊界，驗收測試與新單元測試都有覆蓋。

問題數量：0
