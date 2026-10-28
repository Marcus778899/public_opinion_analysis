PASS 8253391

# QA kafka-commit-retry（PR #145，head 8253391，第二輪）

## 追加 3 條

| 追加 | 結果 |
|---|---|
| R1 開發規格 2.2 不再矛盾 | 「重試期間」「重試上限」兩列已限定 handler（TransientError）；「commit 失敗」列補了 commit 重試不 poll、6 次共約 31.5 秒小於 `max.poll.interval.ms`，並註明調整時要一起檢查。已讀 `git diff d982194 HEAD -- docs` 確認 |
| R2 上限測試 | `test_commit_retry_beyond_limit_raises_after_exactly_six_retries` 斷言 50 個錯誤剩 43（用掉 7 個）；`test_commit_succeeds_on_last_allowed_retry` 給 6 個錯誤，第 7 次成功、`commits == 1` |
| R3 等待中收到 stop | `test_stop_during_commit_retry_wait_leaves_batch_uncommitted`：`wait()` 內自行 set，斷言 `commits == 0`、不拋出、`closed`；覆蓋率缺行由 260–261 變為只剩 266（原 `wait` 之後分支已被覆蓋） |

驗收測試目錄 `tests/unit/acceptance/kafka-commit-retry/`：`git diff 7edaf29 HEAD --stat -- tests/unit/acceptance` 無輸出，未被改動。

## 驗收條件

1. 可重試錯誤退避重試、停止訊號不 commit：驗收測試與單元測試通過（見下）。
2. 超過上限才拋、不可重試照舊拋、失去 assignment 只記 warning：R2 測試與既有測試通過。
3. 每次重試一行 WARNING（code、n/6）：程式碼 `consumer.py` 已讀，驗收測試通過。
4. 驗收測試全過、`make check` 等價（pre-commit 內容為 ruff + `pytest tests/unit`）、CI 全綠：見下。

## 實際執行輸出

```
uv run pytest tests/unit -q          -> 1152 passed in 3.11s
uv run ruff check .                  -> All checks passed!
uv run ruff format --check .         -> 259 files already formatted
uv run pytest tests/unit/common/kafka tests/unit/acceptance/kafka-commit-retry --cov=radar.common.kafka.consumer
  -> 117 passed; consumer.py 96%, Missing 134, 195-197, 266, 277-278
grep -rn "TODO(kafka-commit-retry)" src tests -> 無結果
```

整合測試（開跑前 `docker compose ls` 無其他堆疊；跑完已 `down -v`）：

```
docker compose --env-file .env -f .worktrees/kafka-commit-retry/compose.yaml run --rm test pytest tests/integration/common -q
-> 11 passed in 20.13s
```

CI（head 8253391，`gh pr view 145` headRefOid 確認）：

```
Check             pass 33s
Integration Test  pass 2m5s
Security          pass 26s
```

## 其他檢查

- consumer.py 無寫死 port、網址、token；`_COMMIT_MAX_RETRIES` 為內部可靠性常數，規格已說明理由。
- 禁區：仍為同步 commit，失去 assignment 分支排在重試判斷之前，未改服務入口、相依套件、`scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`。
- 邊界：上限剛好（6 錯第 7 次成功）、超過上限、等待前已 stop、等待中 stop 均有測試。

## 問題

無（0 個）。上輪建議 A（`Event.wait` 與 signal handler 的鎖風險）為非阻擋建議，未列為 FAIL。
