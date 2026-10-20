---
name: domain-knowledge
description: PTT 即時輿情雷達的領域知識。設計或實作爬蟲、ingest、CDC、ClickHouse、標註／推論、熱度偵測、Telegram bot、Dashboard，或判斷 PTT 資料語意（推噓、刪文、post_id、時間）時使用。
---

# PTT 即時輿情雷達：領域知識

這份只放核心規則與索引；細節在 docs，用到才讀。和 CLAUDE.md「資料與架構約定」重複的不再寫。

## 資料流（一句話）

Scheduler／API → `crawl.tasks` → 爬蟲 → `raw.posts`（含推文）→ Ingest → PG `posts`／`comments`
→ Debezium `cdc.public.*` → ClickHouse、標註（`labels`）、推論（`predictions`）、熱度偵測（`alerts`）→ Telegram bot。
全圖見設計文件 2.1；topic 表見設計文件 3.2；各表寫入者見設計文件 5.4。

## 核心規則

- Kafka key：`raw.posts` 用 `post_id`；不用 `board` 當 partition key（負載不均）；不要一個看板開一個 topic
- 爬蟲 instance 數 ≤ `crawl.tasks` 的 partition 數；Scheduler 只能 1 個 instance，不放進 FastAPI
- upsert 一定比較 `crawled_at`（舊快照不覆蓋新資料）；`crawled_at` 不列入變化判斷；變化判斷要含箭頭數與標題（開發規格 7.6、7.24）
- 刪除快照不直接 upsert（會清空推噓與內文）；刪除標記可撤銷且比較 `crawled_at`（開發規格 7.5、7.14）
- 推文要同步而非只新增（樓層會位移，開發規格 7.4、7.15）；一次 INSERT 注意 PG 65535 參數上限
- 會被刪除的 PG 表要 `REPLICA IDENTITY FULL`；ClickHouse 存最新狀態用 ReplacingMergeTree
- 不是每篇都送 LLM（額度，設計文件 7.4、`docs/reports/llm-api-usage.md`）；訓練與評估資料不可重疊
- PTT 網頁版約 10 分鐘才更新推文（開發規格 7.22），「即時」的下限由此決定
- 對 PTT 的請求量有預算（看板頻率下限、`recrawl_min_push`），新增爬取行為前先估請求量（開發規格 7.2）

## 參考檔

- `glossary.md`：術語（PTT 用語、系統內的名詞）
- 常見陷阱完整清單：設計文件第 12 章（新設計前逐條對照）
- 已決定事項：設計文件第 15 章；開發規格第 7 章是各任務的實作選擇與 fix 紀錄
- 情緒標註準則：`docs/labeling-guideline.md`；模型評估：`docs/reports/model-evaluation.md`
