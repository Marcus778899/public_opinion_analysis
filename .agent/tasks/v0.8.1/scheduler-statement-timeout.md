# 派工單 scheduler-statement-timeout

- **類型**：fix
- **負責**：backend
- **目標**：Scheduler 查 PG 時加 statement_timeout，一個查詢卡住不會讓那個看板的派工一直停住（#226）
- **背景**：來源 reports/crawl-backfill-depth.review.md qa 觀察項 2。`latest_post_since`、`DuePostDispatcher` 的查詢沒有逾時，PG 卡住時，該看板這次派工（max_instances=1）會一直等下去。
- **設計依據**：#226；開發規格 7.28 A（續抓）；CLAUDE.md「設定從環境變數讀」
- **相依**：無
- **負責檔案**：
  - `src/radar/collector/scheduler.py`
  - `src/radar/common/db/session.py`（只限加選填的 statement_timeout 參數，預設行為不變）
  - `src/radar/common/settings.py`（只限 scheduler 的逾時設定）
  - `tests/unit/collector/test_scheduler.py`
  - `tests/unit/common/test_settings.py`
  - `tests/unit/common/test_session.py`
  - `.env.example`（只限新增選填設定，依 D-009 寫成註解）
  - `docs/development-spec.md`（只限 scheduler 與逾時設定相關的段落）
- **禁區**：不改其他服務的 PG 連線行為；不改派工規則
- **驗收測試**：
  - `tests/unit/acceptance/scheduler-statement-timeout/`
- **驗收條件**：
  - [ ] Scheduler 的 PG 連線有 statement_timeout，數值從環境變數讀，有合理預設
  - [ ] 查詢逾時時記 WARNING、這一輪略過該看板，下一輪照常派工，服務不會中止
  - [ ] 其他服務用 `session.py` 的方式與行為不變
  - [ ] 文件同步；驗收測試與 `make check` 通過；`grep -rn "TODO(scheduler-statement-timeout)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/scheduler-statement-timeout tests/unit/collector tests/unit/common`；`make check`
- **回報檔**：`reports/scheduler-statement-timeout.json`

## 執行資訊（task.py 產生）

- Issue：#235
- 分支：`fix/scheduler-statement-timeout`（從 develop 開出）
- 工作目錄：`.worktrees/scheduler-statement-timeout`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

manager：`DuePostDispatcher` 在 `src/radar/collector/recrawl.py`，所以把它加進負責檔案。驗收測試已在 85b9304 鎖定，實作要照測試定的介面做：
- 環境變數 `SCHEDULER_STATEMENT_TIMEOUT_SEC`，對應 `SchedulerSettings.statement_timeout_sec`
- `make_engine(..., statement_timeout_sec=None)`

只有逾時（QueryCanceled）這一輪要略過，其他錯誤照現行行為處理。完整的負責檔案清單如下：

- **負責檔案**：
  - `src/radar/collector/scheduler.py`
  - `src/radar/collector/recrawl.py`（只限 `DuePostDispatcher` 的逾時處理）
  - `src/radar/common/db/session.py`（只限加選填的 statement_timeout 參數，預設行為不變）
  - `src/radar/common/settings.py`（只限 scheduler 的逾時設定）
  - `tests/unit/collector/test_scheduler.py`
  - `tests/unit/collector/test_recrawl.py`
  - `tests/unit/common/test_settings.py`
  - `tests/unit/common/test_session.py`
  - `.env.example`（只限新增選填設定，依 D-009 寫成註解）
  - `docs/development-spec.md`（只限 scheduler 與逾時設定相關的段落）
