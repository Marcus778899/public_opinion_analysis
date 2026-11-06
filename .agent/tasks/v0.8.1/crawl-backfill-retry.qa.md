PASS 2974ab7

# crawl-backfill-retry 驗證（PR #230，第二輪：review 退回 7.28 A「正常運作時」）

## 檢查
- 上輪(867fab8)後只動一個 commit 2974ab7：`git diff 867fab8 HEAD --stat` → 只有 `docs/development-spec.md` 1 行（第 1548 列「正常運作時」）；程式與測試未動。
- 該格內容逐字等於 `reports/crawl-backfill-retry.review.md` 指定句子：「第一頁最舊文章通常已不晚於 `since`，只讀一頁，與現在相同；從 `since` 到現在的新文章超過一頁時多讀幾頁到 `since` 為止，這些頁的內頁多數已在快取、不重抓。取代原本固定最多 3 頁」。已無「快取接得上」「約前一分鐘」字樣。
- 與實作一致：crawler.py 停止條件只剩 since 為 null／最舊文章 <= since／無上一頁（`all_new` 已移除）；與同表「翻頁規則」格（第 1543 列）不矛盾。
- 工作目錄 clean（`git status --short` 無輸出）。

## 測試（自己執行，PYTHONPATH 指向 worktree src，import 路徑確認為 worktree 的 crawler.py）
`PYTHONPATH=$PWD/src uv run pytest tests/unit/acceptance/crawl-backfill-retry tests/unit/acceptance/crawl-backfill-depth tests/unit/collector -q`
→ `214 passed in 0.65s`
`uv run ruff check src tests/unit/acceptance` → `All checks passed!`
`grep -rn "TODO(crawl-backfill-retry)" src tests` → 無結果。

## 問題
無。
