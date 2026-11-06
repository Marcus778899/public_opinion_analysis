# 派工單 crawl-backfill-retry

- **類型**：fix
- **負責**：backend
- **目標**：修正補抓途中遇到暫時性錯誤（內頁 429、5xx、逾時）時續抓鏈斷掉的問題（review G1），並補上 7.28 A 的文件缺口
- **背景**：見 `reports/crawl-backfill-depth.review.md` 的 G1 與 qa 觀察項 1：整批重試時一般任務被當積壓略過、續抓任務重讀第一頁時 `all_new` 為假而停止。不比合併前差，但會讓補抓提早結束
- **設計依據**：`docs/development-spec.md` 7.28 A；review 建議修法（`since` 不是 null 時翻頁條件拿掉 `all_new`；「開始處理時間」改為任務處理完、沒拋例外才寫入，值仍是開始時間）。先改 7.28 A（「翻頁規則」列與「略過積壓的列表任務」格，句子照 review 檔）再改程式，同一個 PR
- **相依**：無
- **負責檔案**：
  - `src/radar/collector/crawler.py`
  - `tests/unit/collector/`
  - `docs/development-spec.md`（只限 7.28 A）
- **禁區**：不改訊息格式、scheduler、上限與請求速率
- **驗收測試**：
  - `tests/unit/acceptance/crawl-backfill-retry/`
  - `tests/unit/acceptance/crawl-backfill-depth/test_backfill_crawler_acceptance.py`
- **驗收條件**：
  - [ ] 補抓途中第 N 頁的內頁拋 TransientError、整批重試後，續抓鏈能接著補到 `since`（同一任務重試不被當積壓略過）
  - [ ] `since` 不是 null 時，頁面已有快取文章不再單獨使翻頁停止（仍以最舊文章不晚於 `since`、沒有上一頁、80 頁上限停止）
  - [ ] 7.28 A 已照 review 檔補句並與實作一致
  - [ ] 驗收測試、`make check` 通過；`grep -rn "TODO(crawl-backfill-retry)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/crawl-backfill-retry tests/unit/acceptance/crawl-backfill-depth tests/unit/collector`；`make check`
- **回報檔**：`reports/crawl-backfill-retry.json`

## 執行資訊（task.py 產生）

- Issue：#227
- 分支：`fix/crawl-backfill-retry`（從 develop 開出）
- 工作目錄：`.worktrees/crawl-backfill-retry`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

### reports/crawl-backfill-retry.review.md

REQUEST_CHANGES 867fab8

# crawl-backfill-retry review（PR #230，對照 G1（`reports/crawl-backfill-depth.review.md`）、開發規格 7.28 A）

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 負責檔案 | worker commit 867fab8 只改 `src/radar/collector/crawler.py`、`docs/development-spec.md`（只動 7.28 A 兩格）；禁區（訊息格式、scheduler、上限、速率）沒動 |
| 驗收測試 | 兩個測試檔只在 qa 的 `test(crawl-backfill-retry)` commit 78e9e48 改過；crawl-backfill-depth 的 3 個測試改寫方向符合驗收條件 2 |
| G1 修法①翻頁條件 | `all_new` 已移除（`grep all_new\|cache_was_empty src` 無結果）；停止條件只剩 `since` 為 null、最舊文章不晚於 `since`、沒有上一頁，加上 `max_list_pages`／`max_backfill_pages` 上限，符合 G1 |
| G1 修法②開始時間 | `started = self._clock()` 在讀列表前取值，非 backfill 任務在 `_continue_or_stop` 之後、`return` 前才寫入 `_last_list_start`；拋例外不寫入；值是開始時間；續抓任務仍不寫，符合 G1 與觀察項 1 |
| 邊界推演 | 同一批有兩個同看板列表任務、前一個完成後一個拋例外：重試時前一個被略過，它的續抓任務已送出，不會重複開鏈；後一個比照原有積壓規則判斷，不比合併前差 |
| 7.28 A 補句 | 「翻頁規則」「略過積壓的列表任務」兩格照 review 檔補句，與程式一致 |
| 寫死設定 | 無 |
| 測試 | 自己重跑 `PYTHONPATH=.worktrees/crawl-backfill-retry/src uv run pytest tests/unit/acceptance/crawl-backfill-retry tests/unit/acceptance/crawl-backfill-depth tests/unit/collector` → `214 passed`（確認 import 的是 worktree 的 `crawler.py`）；`grep -rn "TODO(crawl-backfill-retry)" src tests` 無結果。驗收測試涵蓋：重試不被略過、失敗不記時間、記的是開始時間、完成後仍略過較舊任務、三種重試位置的續抓鏈接續、到 `since` 停止、快取不停止翻頁、`since` null 只讀一頁，對得上驗收條件 1、2 |

## 要修改

1. `docs/development-spec.md:1549`（7.28 A「正常運作時」列）— 這格仍寫「快取接得上，第一頁就有見過的文章，只讀一頁」「翻到 `since` 為止（約前一分鐘）」，與本單的翻頁規則矛盾：現在停止與否只看最舊文章是否不晚於 `since`，快取不再參與；`since` 是 PG 最新－10 分鐘，不是「約前一分鐘」。熱門看板 10 分鐘多於一頁新文章時，即使第一頁都見過也會多讀一頁，原句會讓人以為只讀一頁。不符驗收條件 3「與實作一致」與 CLAUDE.md 文件同步規則 — 整格改成：

   > 第一頁最舊文章通常已不晚於 `since`，只讀一頁，與現在相同；從 `since` 到現在的新文章超過一頁時多讀幾頁到 `since` 為止，這些頁的內頁多數已在快取、不重抓。取代原本固定最多 3 頁

   只改這格，不動程式與測試；改完重跑派工單驗證指令。

## 其他（不需處理）

- worker 沒新增 `tests/unit/collector/` 的單元測試；改動的兩處行為由鎖定的驗收測試逐條涵蓋，qa 量得改到的行 100% 覆蓋，接受
