# 派工單 backfill-since-filename

- **類型**：fix
- **負責**：backend
- **目標**：補抓終點 `since` 改用 PG 文章 `post_id` 檔名時間的最大值減 10 分鐘，標頭時間是未來時間時補抓不會停掉（#268）
- **背景**：
  - 資安 v0.8.1 M-1（`docs/security/v0.8.1.md`）：作者把標頭時間改到 2099 年，`since` 永遠在第一頁之後，補抓無聲停用
  - 檔名 epoch 用 `max(split_part(post_id, '.', 3)::bigint)`（Core `select()`），算出晚於現在時以現在計並記 WARNING
  - 刪除文仍計入；沒有文章或查詢失敗為 null；查詢逾時略過這一輪（7.28 A 不變）；parser 不改
- **設計依據**：`docs/development-spec.md` 7.30 E 與派工順序第 3 列、7.28 A；D-042
- **相依**：producer-fatal-exit（已合併）
- **負責檔案**：
  - `src/radar/collector/scheduler.py`
  - `tests/unit/collector/test_scheduler.py`
  - `tests/integration/collector/test_scheduler_since_db.py`（新）
- **禁區**：不改文件（與 7.30 不符時回報 manager）；不改 parser、不碰 `posts.created_at` 的寫法
- **驗收測試**：
  - `tests/integration/acceptance/backfill-since-filename/`
  - `tests/integration/acceptance/crawl-backfill-depth/test_scheduler_since_acceptance.py`（全檔，改用與檔名一致的時間，斷言 `since` 來自檔名時間）
- **驗收條件**：
  - [ ] 真的 PG：`since` = 最大檔名時間 − 10 分鐘
  - [ ] `created_at` 在 2099 年的文章不影響 `since`
  - [ ] 刪除文仍計入；沒有文章為 null；檔名時間晚於現在時以現在計並記 WARNING
  - [ ] `make check` 通過、改到的程式碼覆蓋率達門檻；整合測試通過
- **驗證指令**：`make check`；`docker compose --env-file .env -f .worktrees/backfill-since-filename/compose.yaml run --rm test`（只跑 `tests/integration/acceptance/backfill-since-filename tests/integration/acceptance/crawl-backfill-depth tests/integration/collector`），做完 `down -v`
- **回報檔**：`.agent/reports/backfill-since-filename.json`

## 執行資訊（ae task 產生）

- Issue：#299
- 分支：`fix/backfill-since-filename`（從 develop 開出）
- 工作目錄：`.worktrees/backfill-since-filename`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
