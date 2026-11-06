APPROVE 1555183

# Review consumer-commit-wait（PR #210）

## 檢查項目

| 項目 | 結果 |
|---|---|
| 照 #146 改法 | `_commit()` 的 `self._stop.wait(delay)` 改成 `_sleep_interruptible(delay)`：`deadline = clock() + delay`，`not is_set()` 且 `remaining > 0` 時 `sleep(min(remaining, 0.5))`；`sleep` 可注入，預設 `time.sleep` |
| 禁區 | `_COMMIT_MAX_RETRIES`、`backoff`、可重試錯誤碼都沒有改；其他 consumer 沒有動 |
| 負責檔案 | 只改了 `src/radar/common/kafka/consumer.py`、`tests/unit/common/kafka/test_consumer.py`、`tests/unit/acceptance/consumer-commit-wait/` |
| 驗收測試的來源 | 目錄裡只有 qa 的 `6b3dd91 test(consumer-commit-wait)`，worker 沒有改 |
| 行為不變 | 等待結束後仍檢查 `is_set()`，停止時不 commit 就 return；新參數放在最後、是 keyword 參數，既有呼叫端不受影響；開發規格 2.2 不用改 |
| 寫死設定 | `_SLEEP_SEGMENT_S = 0.5` 是 #146 指定的實作常數，不是部署設定 |
| 改寫的既有測試 | `test_stop_during_commit_retry_wait_leaves_batch_uncommitted` 改成在注入的 sleep 裡 stop；只有一筆 commit 錯誤，停止後如果還重試就會變成 `commits == 1`，所以仍然測到原本的行為 |
| 測試對應驗收條件 | 中途 stop：每段 sleep ≤ 0.5、停止後不再多睡、`commits == 0`、closed、不拋出；另外涵蓋分段加總等於 delay、delay 為 0 不 sleep、不呼叫 `Event.wait`、grep 檢查、開始前已經 stop 的邊界 |

## 實跑（worktree，HEAD 1555183）

- `uv run pytest -q tests/unit/acceptance/consumer-commit-wait tests/unit/common` → `250 passed in 1.22s`
- `grep -rn "_stop.wait" src/radar` → 沒有結果
- `grep -rn "TODO(consumer-commit-wait)" src tests` → 沒有結果

問題數量：0
