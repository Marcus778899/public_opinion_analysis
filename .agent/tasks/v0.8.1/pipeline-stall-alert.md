# 派工單 pipeline-stall-alert

- **類型**：fix
- **負責**：backend
- **目標**：`cdc-watchdog` 偵測資料管線靜默停擺：ClickHouse `posts_history` 最新 `changed_at` 超過 `CDC_WATCHDOG_STALE_ALERT_S`（預設 1800 秒）沒更新就記 ERROR，heartbeat 改 ping `/fail`
- **背景**：10-28 16:18Z 起 kafka_3 coordinator 異常，管線停 10 小時，容器都 Up、沒有任何警告（reports/gossiping-gap-investigate.json）。設計已核可（PR #221）
- **設計依據**：`docs/development-spec.md` 7.28 B（含「自行決定」）、7.16；設計文件 6.4。本單不改文件，實作與文件不符時回報 manager
- **相依**：無（與 `crawl-backfill-depth` 平行）
- **負責檔案**：
  - `src/radar/cdc/watchdog.py`
  - `src/radar/common/settings.py`
  - `src/radar/common/clickhouse.py`
  - `.env.example`
  - `tests/unit/cdc/`
  - `tests/unit/common/test_clickhouse.py`
  - `tests/unit/common/test_settings.py`
  - `tests/integration/cdc/`
- **禁區**：不新增通知管道或套件；不分看板偵測；不改 CDC 恢復流程既有行為
- **驗收測試**：
  - `tests/unit/acceptance/pipeline-stall-alert/`
  - `tests/integration/acceptance/pipeline-stall-alert/`
- **驗收條件**：
  - [ ] 門檻前後的行為、只在狀態改變時記 log、查詢失敗沿用舊值、停擺時 heartbeat 送 `/fail`，皆照 7.28 B
  - [ ] 整合：真的 ClickHouse 讀到 `posts_history` 最新 `changed_at`
  - [ ] `.env.example` 加選填註解 `# CDC_WATCHDOG_STALE_ALERT_S=1800`
  - [ ] 驗收測試、`make check` 通過；`grep -rn "TODO(pipeline-stall-alert)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/pipeline-stall-alert tests/unit/cdc tests/unit/common`；`make check`；整合測試 `docker compose --env-file .env -f .worktrees/pipeline-stall-alert/compose.yaml run --rm test`
- **回報檔**：`reports/pipeline-stall-alert.json`

## 執行資訊（task.py 產生）

- Issue：#223
- 分支：`fix/pipeline-stall-alert`（從 develop 開出）
- 工作目錄：`.worktrees/pipeline-stall-alert`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
