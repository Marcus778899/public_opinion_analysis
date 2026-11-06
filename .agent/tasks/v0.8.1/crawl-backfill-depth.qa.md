PASS 170e310

# crawl-backfill-depth 驗證（PR #225，對照開發規格 7.28 A）

## 執行結果（自己跑的）

- `PYTHONPATH=<worktree>/src uv run pytest -q tests/unit/acceptance/crawl-backfill-depth tests/unit/collector tests/unit/common` -> `451 passed in 1.17s`
- `uv run pytest -q tests/unit` -> `1582 passed in 64.36s`
- `uv run ruff check .` -> `All checks passed!`；`uv run ruff format --check .` -> `309 files already formatted`
- `grep -rn "TODO(crawl-backfill-depth)" src tests` -> 無結果
- 整合（驗收＋collector）`docker compose ... run --rm test pytest -q tests/integration/acceptance/crawl-backfill-depth tests/integration/collector` -> `22 passed in 3.73s`
- 整合全跑 `run --rm test` -> `1 failed, 367 passed`；失敗的是 `tests/integration/dashboard/test_variables.py::test_all_selection_expands_every_option_without_error_for_every_panel`，ClickHouse `code: 241 memory limit exceeded`（8 個 xdist worker 同時查詢）。單獨 `-n0` 重跑該檔 `11 passed`；與本單無關（未動 dashboard/ClickHouse），屬資源爭用造成的不穩定，不列為 FAIL，但列為觀察項
- 已 `down -v` 釋放容器

## 驗收條件逐條

1. 翻頁規則、續抓任務（`since`、`backfill_depth`、`reason=backfill`、key=board、不指定 partition）、80 頁上限記 ERROR（含看板、since、最舊時間）、略過積壓列表任務（backfill 不略過）、`since` null 只讀第一頁：讀 diff 對照 7.28 A 表格逐項一致；驗收單元測試 451 passed。PASS
2. 整合：Scheduler `since` = PG 該看板最新 `created_at` − 10 分鐘，無文章為 null：驗收整合測試（真 PG）通過；查詢失敗回 null 並記 WARNING，符合 7.28 A。PASS
3. e2e：**未實跑**（e2e 與開發環境共用容器名稱 #41，開發環境運作中，依指示不起 e2e 堆疊）。檢查寫法：假 PTT 新增分頁（page_size 控制端點、`indexN.html`、上頁連結），有 4 個單元測試覆蓋；e2e 測試把頁大小設 2、先確認首篇入 PG（讓 Scheduler 有 since）、停爬蟲、新增 8 篇（共 9 篇＝5 頁，超過每任務 3 頁）、重啟後等全部入 PG，逾時 240 秒。邏輯合理，推演 5 頁都會讀到（第 3 頁後送續抓）。未實跑須由甲方／之後在 e2e 環境確認
4. 驗收測試、lint、unit 通過；`make check` 等同的 pre-commit 在 sandbox 只跑了 ruff check/format（通過），其餘為 worker 回報 pre-commit all Passed（未自行重跑，非 FAIL 理由）

## 邊界與寫死設定

- 80 頁剛好讀完且已到 since：不記 ERROR（合理）；到 80 頁仍要翻：記 ERROR 且不送續抓
- 最舊文章時間解析不出來（oldest None）：停止翻頁，保守
- 列表頁抓取失敗：鏈中斷（沿用既有失敗處理），可接受
- 新增程式沒有寫死 port、網址、token（grep 無結果）；`SINCE_MARGIN`、`max_backfill_pages=80` 為文件規定的常數／建構參數
- schema：post 任務帶 `since`、`backfill_depth!=0`、`reason=backfill` 會驗證失敗，符合 3.1

## 自行決定的判斷：reason=backfill 不更新「最近一次開始處理時間」

合理，且不與 7.28 A 矛盾：文件只說「`reason` 不是 `backfill` 且 `created_at` 早於這個時間的任務略過」，續抓不被略過；若續抓也更新時間，補抓期間排入的 schedule 任務（created_at 早於續抓開始）會被誤略過，違背「補到 since」的目的。屬文件缺口，建議 manager 在 7.28 A 該列補一句「續抓任務不更新此時間」。

## 觀察項（非 FAIL）

- 文件缺口：上述續抓不更新時間
- `latest_post_since` 沒有獨立 statement timeout（worker 已回報），PG 卡住時會阻塞 Scheduler 該次派工
- e2e 新測試未實跑
- 整合全跑的 dashboard 記憶體不穩定（上述）
