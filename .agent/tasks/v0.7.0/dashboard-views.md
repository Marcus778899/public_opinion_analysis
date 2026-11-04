# 派工單 dashboard-views

- **類型**：feat
- **負責**：backend
- **目標**：新增 ClickHouse migration 0005，建立 dashboard 用的兩個一般 view：post_votes、post_sentiment_latest（開發規格 7.25 派工順序 2）
- **背景**：dashboard-grafana-infra 已合併（PR #100），唯讀帳號 grafana 可查 radar DB。view 收斂 bot/stats.py 的 POST_STATS_QUERY 邏輯，面板與驗收測試都查它。已合併的 migration 不可改，只能新增
- **設計依據**：`docs/development-spec.md` 7.25（查詢來源、測試環境）、7.26；`docs/realtime-sentiment-radar-design.md` 6.3；D-014
- **相依**：dashboard-grafana-infra（已合併）
- **負責檔案**：
  - `infra/clickhouse/migrations/0005_dashboard_views.sql`
  - `docs/development-spec.md`
  - `docs/realtime-sentiment-radar-design.md`
- **禁區**：不改 0001～0004 migration；不建 materialized view；不改 `src/`（bot/stats.py 不改用 view，留給之後）；不改 grafana 設定與 dashboard JSON；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：
  - `tests/integration/acceptance/dashboard/test_views.py`
- **驗收條件**：
  - [ ] 驗收測試全過：radar DB 放種子資料、以唯讀帳號查 view，刪除的推文不計、取最新一筆推論、沒有推論的文章不出現
  - [ ] `make check` 通過；`docker compose --env-file .env -f .worktrees/dashboard-views/compose.yaml run --rm test` 全過並附輸出；交單前 down -v
  - [ ] 設計文件 6.3（或對應的表清單）與開發規格 7.25 列出兩個 view 與欄位
  - [ ] PR 的 CI 全綠
- **驗證指令**：`make check`；`docker compose --env-file .env -f .worktrees/dashboard-views/compose.yaml run --rm test`
- **回報檔**：`reports/dashboard-views.json`

## 執行資訊（task.py 產生）

- Issue：#104
- 分支：`feat/dashboard-views`（從 develop 開出）
- 工作目錄：`.worktrees/dashboard-views`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-21

architect 仲裁 TEST_OK（reports/dashboard-views.ruling.md）：驗收測試沒錯，錯在既有 cdc 測試對 labels、predictions 查整張表。照仲裁檔修：該測試的兩個查詢限定自己的 post_id，並更新開發規格 7.26 對應那一列。負責檔案以下列為準（整份重列，含新增的 cdc 測試檔）：

- **負責檔案**：
  - `infra/clickhouse/migrations/0005_dashboard_views.sql`
  - `tests/integration/cdc/test_clickhouse_migrations.py`
  - `docs/development-spec.md`
  - `docs/realtime-sentiment-radar-design.md`

改完重跑 `docker compose --env-file .env -f .worktrees/dashboard-views/compose.yaml run --rm test`（全過、附輸出、做完 down -v），commit、更新回報（disputes 清空、status 改回）。
