# 派工單 crawl-backfill-depth

- **類型**：fix
- **負責**：backend
- **目標**：爬蟲重啟或停擺後，依 scheduler 給的 `since` 往前補抓到 PG 最新文章為止（續抓任務、80 頁上限、略過積壓的列表任務）
- **背景**：#180 調查（reports/gossiping-gap-investigate.json）：重啟後只抓第一頁，Gossiping、HatePolitics 漏約 1 萬篇。設計已核可（PR #221）
- **設計依據**：`docs/development-spec.md` 7.28 A（含「自行決定」）、3.1（`crawl.tasks` 新欄位）、2.2；設計文件 4.2、4.4、4.6。本單不改文件，實作與文件不符時回報 manager
- **相依**：無（與 `pipeline-stall-alert` 平行）
- **負責檔案**：
  - `src/radar/common/schemas.py`
  - `src/radar/common/enums.py`
  - `src/radar/common/tasks.py`
  - `src/radar/collector/crawler.py`
  - `src/radar/collector/scheduler.py`
  - `tests/unit/collector/`
  - `tests/unit/common/test_schemas.py`
  - `tests/unit/common/test_tasks.py`
  - `tests/integration/collector/`
  - `tests/e2e/fake_ptt.py`
  - `tests/e2e/test_pipeline.py`
- **禁區**：爬蟲不碰 PG；不改 API 手動觸發；不改最高請求速率
- **驗收測試**：
  - `tests/unit/acceptance/crawl-backfill-depth/`
  - `tests/integration/acceptance/crawl-backfill-depth/`
- **驗收條件**：
  - [ ] 翻頁規則、續抓任務內容（`since`、`backfill_depth`、`reason=backfill`）、80 頁上限記 ERROR、略過積壓的列表任務（續抓不略過）、`since` 為 null 時只讀第一頁，皆照 7.28 A
  - [ ] 整合：scheduler 的 `since` 取該看板 PG 最新 `created_at` 減 10 分鐘，沒有文章時為 null
  - [ ] e2e：假 PTT 放超過 3 頁新文章後重啟爬蟲，全部補到
  - [ ] 驗收測試、`make check` 通過；`grep -rn "TODO(crawl-backfill-depth)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/crawl-backfill-depth tests/unit/collector tests/unit/common`；`make check`；整合測試 `docker compose --env-file .env -f .worktrees/crawl-backfill-depth/compose.yaml run --rm test`
- **回報檔**：`reports/crawl-backfill-depth.json`

## 執行資訊（task.py 產生）

- Issue：#222
- 分支：`fix/crawl-backfill-depth`（從 develop 開出）
- 工作目錄：`.worktrees/crawl-backfill-depth`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
