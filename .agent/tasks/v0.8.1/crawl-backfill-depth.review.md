APPROVE 170e310

# crawl-backfill-depth review（PR #225，對照開發規格 7.28 A、3.1）

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 負責檔案 | 15 個檔案都在派工單範圍內（`tests/unit/collector/test_fake_ptt_paging.py` 屬 `tests/unit/collector/`）；API 手動觸發、`RateLimiter` 沒動 |
| 驗收測試 | `git diff 757dff6..170e310 -- tests/*/acceptance` 沒有變更，worker 沒改 qa 的測試 |
| 3.1 訊息格式 | `CrawlTask` 加 `since`、`backfill_depth`（`ge=0`）、`CrawlReason.BACKFILL`；post 任務帶任何一項就驗證失敗；`schema_version` 不變 |
| Scheduler 查 since | `latest_post_since`：Core `select(func.max(Post.created_at)).where(Post.board == board)`、參數綁定、同一個 engine；沒有文章或查詢失敗（WARNING）→ null；`SINCE_MARGIN` 10 分鐘 |
| 翻頁規則 | `since` 不是 null、`all_new`、最舊文章時間（`created_at_from_filename`）晚於 `since`、有上一頁，四項全成立才翻；`cache_was_empty` 已移除 |
| 每任務 3 頁、續抓 | 讀滿 `max_list_pages` 還要翻 → `model_copy` 送續抓：新 `task_id`、`reason=backfill`、`url`=上一頁、`since` 照抄、`backfill_depth`=鏈已讀頁數、key=`board`、不指定 partition；`__call__` 結尾 `flush()` 在 commit 前 |
| 80 頁上限 | `max_backfill_pages=80` 建構參數；到上限還要翻才記 ERROR（看板、since、最舊時間），剛好讀完不記 |
| 略過積壓 | 非 backfill 任務 `created_at` 早於該看板最近一次開始時間就略過；backfill 不略過；狀態在記憶體，重啟清空 |
| 寫死設定 | 沒有新的 port、網址、token；常數皆為 7.28 A 規定值 |
| 測試 | 自己重跑 `PYTHONPATH=<worktree>/src uv run pytest tests/unit/acceptance/crawl-backfill-depth tests/unit/collector` → `204 passed`；`grep TODO(crawl-backfill-depth)` 無結果；qa 已跑整合（真 PG）通過 |
| e2e 寫法 | 假 PTT 檔名用 epoch（`created_at_from_filename` 解得出），頁大小 2、9 篇＝5 頁；推演：第一條讀 5→4→3 頁送續抓，續抓讀 2→1 頁、沒有上一頁停止，全部補到 |

## 設計缺口（非本單偏離，不擋合併；我是設計者，需開後續單）

**G1 補抓途中遇到 TransientError，續抓鏈就斷**：`fetch_and_publish_post` 只接 `FetchError`，內頁 429／5xx／逾時的 `TransientError` 往上丟、整批重試。重試時（a）一般任務的 `created_at` 早於上次記下的開始時間，被當成積壓略過；（b）續抓任務重讀本條第一頁，那頁已全部進快取，`all_new` 為假，停止且不送續抓。兩種都讓更早的頁不再補。24 小時停機約 1,400 次請求，遇到一次 429 或逾時的機率不低。結果退回到本單之前的行為（只補已讀的頁），不比 develop 差，所以不擋合併。
建議修法（技術細節，architect 自行決定，先改 7.28 A 再實作）：

- 翻頁條件：`since` 不是 null 時拿掉 `all_new`，只看「最舊文章時間晚於 `since`」與「有上一頁」（正常運作時 `since`≈PG 最新－10 分鐘，第一頁通常就到 `since`，多翻一頁的內頁多數在快取不重抓）
- 開始處理時間：改在任務處理完（沒有拋例外）才寫入，值仍是開始時間；重試的同一個任務不會被略過

## qa 觀察項的判斷

| # | 觀察項 | 判斷 |
|---|---|---|
| 1 | 續抓不更新開始處理時間 | 合理且必要：一條鏈最多約 2.4 小時，若續抓也更新，這段期間排入的一般任務全被略過，看板最新文章延遲到補抓結束。是 7.28 A 的文件缺口，要補的句子見下 |
| 2 | `latest_post_since` 沒有獨立 statement timeout | 不擋合併。`BlockingScheduler` 每個看板計時器在執行緒池各自執行（`max_instances=1`、`coalesce=True`），PG 卡住只卡住該看板那次派工；`DuePostDispatcher` 共用同一個 engine，原本就有同樣的風險，不是本單引入。另開 backlog：Scheduler 的 engine 加 `statement_timeout`（兩者一起受益） |
| 3 | e2e 新測試未實跑 | 程式碼層面可接受合併（上表推演無誤、假 PTT 分頁有單元測試）；但驗收條件 3 仍是「未驗證」，不可勾選。manager 要在 BOARD「卡住」記一筆，發版前在 e2e 環境跑 `test_crawler_restart_backfills_more_than_three_pages`；另外合併後 `make up-app` 重啟本身就是一次真實補抓，可看爬蟲 log 是否出現續抓與 `list ... done` 的頁數作為輔證 |

### 觀察項 1 要補的文件（開發規格 7.28 A「略過積壓的列表任務」那列，取代整格）

> 爬蟲記住每個看板最近一次開始處理列表任務的時間；`reason` 不是 `backfill` 且 `created_at` 早於這個時間的列表任務直接略過（同 7.12 的道理：之後已經讀過更新的列表）。續抓任務不更新這個時間：一條鏈最多約 2.4 小時，若更新，這段期間排入的一般任務都會被略過，看板最新文章要等補抓結束才抓。重啟後清空

（若採納 G1 的修法，同一格再加「任務處理完才寫入，整批重試時同一個任務不會被略過」，並在「翻頁規則」列改成 G1 的條件。）

## 其他（不需處理）

- 開始時間用爬蟲的時鐘、`created_at` 用 Scheduler 的時鐘；目前同一台主機。上雲（階段 9）分機器時要注意時鐘偏差，屆時再看
- qa 回報整合全跑的 dashboard ClickHouse 記憶體不穩定，與本單無關
