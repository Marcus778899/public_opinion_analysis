APPROVE 7052432

# Review pipeline-stall-alert（PR #224）

依據：派工單 `tasks/pipeline-stall-alert.md`、開發規格 7.28 B（含「自行決定」）、7.16、設計文件 6.4（第 474 行）。

## 檢查項目

| 項目 | 結果 |
|---|---|
| 改動範圍 | 7 個檔都在負責檔案內；驗收測試兩個目錄只有 qa 的 `cc0c2dc test(pipeline-stall-alert)` 改過，worker 沒動 |
| 訊號 | `read_latest_changed_at` 查 `SELECT max(changed_at) FROM posts_history`；欄位是 `DateTime64(3, 'UTC')`（migration 0001），`.replace(tzinfo=UTC)` 正確；空表回 epoch → None |
| 落後計算 | `FreshnessWatch.observe`：`now − max(最後查到的值, started_at)`，`>` 門檻才算停擺（剛好等於門檻不告警），只在狀態改變時回傳 transition；較舊的值不會讓 `_latest` 倒退 |
| 查詢失敗 | `check_freshness` 接住 `ClickHouseError`、`httpx2.HTTPError`、`KeyError`、`ValueError`（含 JSON 解析錯誤）記 WARNING、沿用舊值；ClickHouse 停太久會在門檻後告警，同 7.28 B |
| 通知 | 進入停擺記 ERROR 一次、恢復記 INFO 一次；`is_cdc_healthy` 在 stalled 時回 False，`run_once` 送 `/fail`；沒有新管道或套件 |
| 時鐘 | 用 `datetime.now(UTC)`（牆上時鐘），`wall_now` 可注入；connector／slot 仍用 `time.monotonic()`，既有行為不變 |
| 連線 | 沿用 `ClickHouseSettings`；`ClickHouseClient` 加 keyword-only `timeout_s`（預設 30.0 不變，既有呼叫端不受影響）；watchdog 傳 `request_timeout_s`；結束時 `clickhouse.close()` |
| 設定 | `CdcWatchdogSettings.stale_alert_s = 1800.0`；`.env.example` 加選填註解 `# CDC_WATCHDOG_STALE_ALERT_S=1800`（D-009）；沒有寫死的 port、網址、token |
| CDC 恢復流程 | `check_connector`、`check_slot` 未改；`is_cdc_healthy` 第三個參數預設 None，舊呼叫行為不變 |
| 安全 | SQL 是常數，沒有使用者輸入；WARNING 只記例外 repr，ClickHouse 帳密在 header，不會進 log |
| 測試是否測到驗收條件 | 單元驗收測試涵蓋門檻前／剛好／之後、只報一次、恢復、再次停擺、啟動時間下限、空表、查詢失敗沿用舊值與門檻後告警、heartbeat `/fail` 與恢復後回 base URL、設定預設與環境變數、`.env.example`、`timeout_s`；整合驗收測試用真的 ClickHouse 讀最大值、跟著新列前進、空表 |

## 實際執行（PYTHONPATH 指向本 worktree 的 src，已確認 import 路徑是 worktree 的 `watchdog.py`）

- `PYTHONPATH=$PWD/src uv run pytest -q tests/unit/acceptance/pipeline-stall-alert tests/unit/cdc tests/unit/common` → `315 passed`
- `uv run ruff check .` → All checks passed；`uv run ruff format --check .` → 307 files already formatted
- `grep -rn "TODO(pipeline-stall-alert)" src tests` → 無結果
- 整合測試沒有重跑，採用 qa 證據（`reports/pipeline-stall-alert.qa.md`：14 passed）與 worker 回報（364 passed）

## 非阻擋備註（不需在本單修）

- `watchdog.py` `check_freshness` 的 ERROR 訊息印的是這一輪的 `latest`；停擺是因查詢失敗時會印成 `None`，不是最後一次查到的時間。只影響訊息可讀性
- worker 的 open question（`cdc-watchdog` 容器是否帶 `CLICKHOUSE_*`）已由 qa 對照 `infra/docker-compose.yaml` 確認（`env_file` 加 `app-env` 的 `CLICKHOUSE_URL`），不成立
