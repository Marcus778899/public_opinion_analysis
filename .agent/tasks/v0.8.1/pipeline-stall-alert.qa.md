PASS 7052432

# QA pipeline-stall-alert（PR #224，commit 7052432）

## 驗收條件
1. 門檻前後、只在狀態改變時記 log、查詢失敗沿用舊值、停擺時 heartbeat `/fail`：對照 `src/radar/cdc/watchdog.py` 與開發規格 7.28 B 一致（`落後 = now − max(最新 changed_at, 啟動時間)`；`FreshnessWatch.observe` 只在狀態改變時回傳 transition，才記 ERROR／INFO；查詢失敗記 WARNING 並沿用舊值；`is_cdc_healthy` 在 stalled 時回 False，`run_once` 據此送 `/fail`；`ClickHouseClient` 加 `timeout_s`，watchdog 傳 `request_timeout_s`）。單元＋驗收測試通過（下）。PASS
2. 整合（真 ClickHouse 讀 `posts_history` 最新 `changed_at`）：PASS
3. `.env.example` 有 `# CDC_WATCHDOG_STALE_ALERT_S=1800`（選填註解，diff 已確認）：PASS
4. 驗收測試、`make check` 通過、無殘留 TODO：PASS

## 實際執行
- `PYTHONPATH=$PWD/src uv run pytest -q tests/unit/acceptance/pipeline-stall-alert tests/unit/cdc tests/unit/common` → `315 passed in 1.08s`
- `uv run pytest -q tests/unit -n 4` → `1559 passed in 58.67s`
- `make check` 的內容：`uv run pre-commit run --all-files` 全部 Passed（trailing whitespace、end of files、check yaml、ruff、ruff format、bandit）；`uv run ruff check .` → All checks passed；`ruff format --check` → 307 files already formatted。（make 本身未直接執行，因含 docker／sandbox 限制；以其組成指令代替）
- `grep -rn "TODO(pipeline-stall-alert)" src tests` → 無結果
- 整合：`docker compose --env-file .env -f .worktrees/pipeline-stall-alert/compose.yaml run --rm test pytest -q tests/integration/acceptance/pipeline-stall-alert tests/integration/cdc` → `14 passed in 14.84s`；之後已 `down -v`

## 指定檢查：cdc-watchdog 是否帶到 CLICKHOUSE_* 變數
- `infra/docker-compose.yaml` 的 `cdc-watchdog` 以 `<<: *app`（含 `env_file: ../.env`）繼承，`environment` 帶 `<<: *app-env`（含 `CLICKHOUSE_URL: http://clickhouse:8123`）
- `ClickHouseSettings` 需要 `CLICKHOUSE_USER`、`CLICKHOUSE_PASSWORD`（必填）、`CLICKHOUSE_DB`（預設 radar）、`CLICKHOUSE_URL`。`.env.example` 第 61～64 行有這四個變數名稱，使用者 `.env` 依範本建立就會經 `env_file` 帶進容器；URL 由 app-env 覆寫為容器網路位址
- 結論：不需修改 compose，風險不成立（未讀 `.env` 內容，只以變數名稱比對 `.env.example`）。附註：`cdc-watchdog` 沒有 `depends_on: clickhouse`，但 ClickHouse 連不上只會記 WARNING 並沿用舊值，不會使 watchdog 失敗

## 邊界與寫死值
- 空表（epoch）回 None，以啟動時間當下限，不會一開機就告警；查詢例外（ClickHouseError、HTTP、KeyError、ValueError）皆被接住
- 新增程式沒有寫死的 port／網址／token
- 低風險備註（不列 FAIL）：`main()` 裡的接線（建立 ClickHouseClient、傳入 `run_once`）沒有單元測試，由 `run_once` 的測試間接涵蓋；`mypy` 專案未安裝，未跑型別檢查

問題數量：0
