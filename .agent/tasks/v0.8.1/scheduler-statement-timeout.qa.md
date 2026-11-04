PASS 3a7f5c0

# QA 證據 scheduler-statement-timeout（PR #239，HEAD 3a7f5c0）

## 驗收條件

| 條件 | 結果 | 證據 |
|---|---|---|
| Scheduler 的 PG 連線有 statement_timeout，環境變數、有預設 | PASS | `SchedulerSettings.statement_timeout_sec`（`SCHEDULER_STATEMENT_TIMEOUT_SEC`，預設 30.0）；`main()` 傳給 `make_engine(statement_timeout_sec=)`；真實 PG `show statement_timeout` = `300ms`（設 0.3 秒） |
| 逾時記 WARNING、略過該看板這一輪、下一輪照常、不中止 | PASS | 真實 PG 驗證，見下 |
| 其他服務用 session.py 行為不變 | PASS | `grep make_engine(` 只有 scheduler 傳新參數；ingest／api／bot／backfill_hash 未改；真實 PG 預設 engine `show statement_timeout` = `0`，`pg_sleep(0.6)` 不逾時 |
| 文件同步、測試與 check 通過、無 TODO | PASS | 開發規格 7.28 A 加「查詢逾時」列、`.env.example` 有註解項；`grep -rn "TODO(scheduler-statement-timeout)" src tests` 無結果（exit 1） |

## 自己執行的指令與輸出

PYTHONPATH 指向 worktree 的 src：

```
uv run pytest tests/unit/acceptance/scheduler-statement-timeout tests/unit/collector tests/unit/common -q
427 passed in 1.49s

uv run pytest tests/unit -q -n auto
1668 passed in 56.92s

uv run ruff check .          -> All checks passed!
uv run ruff format --check . -> 315 files already formatted
pre-commit run --all-files   -> trim trailing whitespace / fix end of files / check yaml / ruff / ruff format / bandit 全部 Passed
```

（`make check` = pre-commit run --all-files + pytest tests/unit，兩者皆實際跑過。）

## 真實 PG 驗證（整合測試 compose 的 postgres，radar_it；worker 沒做過）

`docker compose --env-file .env -f .worktrees/scheduler-statement-timeout/compose.yaml run --rm test python -c '...'`，`make_engine(statement_timeout_sec=0.3)`：

```
show: 300ms
1 type: OperationalError orig: psycopg.errors QueryCanceled is_query_timeout: True      # pg_sleep(3)
1b type: DataError DivisionByZero is_query_timeout: False                              # 其他錯誤不被誤判
default show: 0
default no timeout ok                                                                   # 不傳參數的 engine，pg_sleep(0.6) 不逾時
2 latest_post_since raised OperationalError timeout: True 0.31 s                        # 另一連線對 posts 取 ACCESS EXCLUSIVE 鎖
[WARNING] query latest post of Gossiping timed out, skipping this round: OperationalError('(psycopg.errors.QueryCanceled) canceling statement due to statement timeout')
2b sender returned; send called: False 0.31 s
[WARNING] find due posts timed out, skipping this round: OperationalError('(psycopg.errors.QueryCanceled) ...')
2c dispatcher returned 0 send called: False 0.31 s
```

釋放鎖後下一輪（第二次執行，partition_count 設 3；第一次 step 3 的 TypeError 是我的 MagicMock 沒設 partition_count，非實作問題）：

```
3 next round (no lock) send called: True since: None
3b dispatcher after: 0
```

結論：真實 PG 的 QueryCanceled 確實以 `OperationalError`、`.orig` 為 `psycopg.errors.QueryCanceled` 出現，`is_query_timeout()` 認得；兩條路徑都在約 0.3 秒內逾時、記 WARNING、略過該輪，鎖釋放後下一輪正常派工。測完已 `down -v`，容器、網路、volume 全部移除。

## 觀察（不列為 FAIL，供參考）

1. `statement_timeout_sec` 沒有範圍驗證：0 代表不逾時（PG 語意），負值會讓 PG 連線選項出錯；預設值正常，屬設定錯誤情境。
2. `DuePostDispatcher` 只對 `find_due_posts` 的逾時處理；送完 Kafka 後 `record_dispatch`／commit 若逾時會往上拋，由 `_logged` 記錄、下輪重試（開發規格已寫「寫 DB 失敗只會重複派發，無害」），符合派工單「只有查詢逾時略過」。
3. statement_timeout 也套到 AdvisoryLock 共用的 engine，其查詢皆非阻塞，無影響（worker 已在 open_questions 說明）。
4. 無寫死的 port、網址、token。
