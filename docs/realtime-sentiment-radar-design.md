# 即時輿情雷達：設計草案

> 狀態：實作中（階段 1～4 已驗收；階段 5 MVP 待 3 天驗收；進度見開發規格第 6 章）
> 最後更新：2026-10-21（階段 8 規劃：shadow 推論、模型包，開發規格 7.27）
>
> 本文件需與程式同步：改動資料流、表、topic、訊息格式時先更新這裡（CLAUDE.md）。

## 目錄

1. [產品定位](#1-產品定位)
2. [整體架構](#2-整體架構)
3. [Kafka Topic 規劃](#3-kafka-topic-規劃)
4. [資料收集](#4-資料收集)
5. [Ingest：Kafka → PostgreSQL](#5-ingestkafka--postgresql)
6. [CDC 與 ClickHouse](#6-cdc-與-clickhouse)
7. [離線 ML](#7-離線-ml)
8. [線上串流處理](#8-線上串流處理)
9. [呈現層](#9-呈現層)
10. [程式結構與部署](#10-程式結構與部署)
11. [資源估算](#11-資源估算)
12. [常見陷阱](#12-常見陷阱)
13. [實作順序](#13-實作順序)
14. [延伸功能](#14-延伸功能)
15. [已決定事項](#15-已決定事項)

---

## 1. 產品定位

追蹤 PTT 等社群上的話題，在討論**開始發酵時**偵測並通知使用者，同時告訴使用者這個話題的**風向**。

- **主要介面是 Telegram bot**：警示推送，與用按鈕選單管理訂閱、查詢熱門與看板概況（9.2）；Dashboard 看長時間的趨勢（9.1）
- **兩類訊號**：
  - 熱度：推文增加的速度（8.3）
  - 風向：文章本身的情緒（模型推論，8.2）、共鳴度與爭議度（推、噓、箭頭的數量與比例，15.6）。推文內容的情緒（群眾反應）列為延伸功能（14.4）
- **即時性**：受 PTT 網頁版約 10 分鐘的更新週期限制（4.2）；要更即時需改用 PTT BBS（開發規格「後續階段」）
- 每日話題摘要（LLM）為非 MVP 功能

### 1.1 為什麼用 Kafka

- 爬蟲高頻輪詢，資料持續流入
- 同一份變化要同時分送給多個速度不同的下游（ClickHouse、LLM 標註、推論、熱度偵測）
- 多個爬蟲 instance 需要緩衝層與 DB 解耦
- 模型迭代時可以開新的 consumer group 做 shadow 比較

> 如果改做「每日報告」，就該拿掉 Kafka，改用 cron + ETL。

---

## 2. 整體架構

### 2.1 架構圖

完整版（含模組對應與階段分組）見 [architecture.drawio.svg](architecture.drawio.svg)。

```
 管理者 ──→ FastAPI ──→ PG: boards（看板設定）
                ↑ GET /boards（每 30 秒）
            Scheduler
                ↓
        Kafka: crawl.tasks
                ↓
        爬蟲 × N
                ↓
        Kafka: raw.posts（含推文，key = post_id）
                ↓
        Ingest consumer（帶條件 upsert）
                ↓
        PG: posts, comments（source of truth）
                ↓
        Debezium CDC
                ↓
        Kafka: cdc.public.posts / cdc.public.comments（Apicurio 管理 schema）
     ┌──────────┬──────────┬──────────┬──────────┐
     ↓          ↓          ↓          ↓
 ClickHouse   標註        推論        熱度偵測（Quix Streams）
              ↓          ↓          ↓
           labels    predictions   alerts → Telegram bot
              └──────────┴──→ ClickHouse → Dashboard / 訓練資料
```

### 2.2 兩條線

| 線 | 頻率 | 流程 |
|---|---|---|
| 線上串流 | 持續運作 | 爬蟲 → Kafka → PG → CDC → Kafka → 推論 / 熱度 → 儲存 → 通知 |
| 離線 ML | 偶爾執行 | 抽樣 → LLM 標註 → 人工抽查 → 訓練 → 評估 → 發佈模型 |

### 2.3 元件職責

| 元件 | 數量 | 職責 |
|---|---|---|
| FastAPI | 1 | 中央管理：看板設定、手動觸發、系統狀態 |
| Scheduler | **只能 1** | 依設定派發爬取任務 |
| 爬蟲 | N | 執行任務，不知道任何設定 |
| Ingest consumer | 1+ | 批次 upsert 進 PG，把快照轉成差異 |
| PostgreSQL | 1 | Source of truth |
| Debezium | 1 | 把 PG 的變化轉成事件 |
| CDC watchdog | 1 | 監看 connector 與 replication slot，task 失敗時自動重啟（6.4） |
| Apicurio | 1 | Schema Registry |
| ClickHouse | 1 | OLAP 分析、熱度曲線、訓練資料來源 |
| Telegram bot | 1 | 推送警示（熱度、推噓與爭議度、文章情緒）與每日摘要；按鈕選單管理訂閱、查詢熱門與看板概況 |

---

## 3. Kafka Topic 規劃

### 3.1 原則

- **看板是訊息欄位，不是 topic**：topic 數量與看板數量無關
- **Partition key 用 `post_id`**：用 `board` 會因 Gossiping 量大造成負載不均
- **例外：`crawl.tasks` 的列表任務 key 用 `board`**，讓同一看板固定由同一個爬蟲處理，爬蟲才能在記憶體記住列表推文數（4.2）；文章任務仍用 `post_id`
- 列表任務的 partition 不靠 key 的 hash，而是依啟用中看板的名稱排序**輪流指定**，避免多個看板擠在同一個 partition（開發規格 7.10）

### 3.2 業務 topic

| Topic | Producer | Consumer | Partitions | 保留 |
|---|---|---|---|---|
| `crawl.tasks` | Scheduler、FastAPI | 爬蟲 | 3 | 1 天 |
| `raw.posts` | 爬蟲 | Ingest | 3 | 7 天 |
| `raw.html` | 爬蟲 | 重新解析時使用 | 3 | 3 天（zstd） |
| `cdc.public.posts` | Debezium | ClickHouse、標註、推論 | 3 | 7～14 天 |
| `cdc.public.comments` | Debezium | ClickHouse、熱度偵測 | 3 | 7～14 天 |
| `labels` | 標註 | ClickHouse | 3 | 30 天 |
| `predictions` | 推論 | ClickHouse | 3 | 30 天 |
| `predictions.shadow` | shadow 推論（8.4） | ClickHouse | 3 | 30 天 |
| `alerts` | 熱度偵測 | Telegram bot、ClickHouse | 1 | 7 天 |
| `dlq` | 各 consumer | 人工檢查 | 1 | 30 天 |

- CDC topic 命名規則：`<topic.prefix>.<schema>.<table>`
- `raw.posts` 包含推文，不拆出 `raw.comments`（見 15.5）
- 爬蟲 instance 數不超過 `crawl.tasks` 的 partition 數

### 3.3 系統 topic

| Topic | 來源 |
|---|---|
| `__consumer_offsets` | Kafka |
| `connect_configs` / `connect_offsets` / `connect_statuses` | Kafka Connect |
| `__debezium-heartbeat.cdc` | Debezium heartbeat（broker 不自動建 topic，列在 `topics.yaml`） |
| `changelog__*` / `repartition__*` | Quix Streams（2～4 個） |

Apicurio 使用 SQL 儲存，不建立 topic。PG connector 不需要 schema history topic。

**合計約 16～18 個 topic。**

---

## 4. 資料收集

### 4.1 資料來源

- 第一階段：PTT `Gossiping`、`Stock`、`Tech_Job`（帶 `over18` cookie）、RSS
- 之後：Dcard（有 Cloudflare 防護）、Reddit

### 4.2 輪詢策略

#### 新文章：輪詢看板列表頁

- 頻率依看板設定（`boards.interval_sec`，下限 30 秒）
- **列表推文數快取**：爬蟲在記憶體以 LRU 記住 `post_id → 列表推文數`，沒見過或推文數變了才抓內頁
  - 「爆」固定視為 100，所以「爆 → 爆」算沒變，由 4.5 的重爬排程定期抓；「99 → 爆」算變化
  - 被刪除的文章（列表上沒有連結）不抓
  - 爬蟲重啟或 rebalance 後快取清空，只會多抓幾次內頁，upsert 會擋掉沒變化的寫入
- **往前翻頁**：第一頁的文章全都沒見過、且快取不是空的，代表兩次輪詢間新文章超過一頁，再往前翻，最多 3 頁；剛啟動（快取為空）只讀一頁
- 置底公告（`r-list-sep` 以下）不列入

#### 近期文章：依年齡分級重爬

PTT 網頁版的文章頁約 10 分鐘才更新一次（開發規格 7.22），重爬再密也拿不到更新的內容；即時性的下限約 10 分鐘，要更低需改用即時的資料來源（PTT BBS，見開發規格「後續階段」）。

| 文章年齡 | 重爬頻率 |
|---|---|
| < 1 小時 | 每 5 分鐘 |
| 1～6 小時 | 每 10 分鐘 |
| 6～24 小時 | 每小時 |
| > 24 小時 | 停止 |

**重爬門檻**：文章滿 1 小時後，推文總數（推、噓、箭頭都算）低於該看板的 `boards.recrawl_min_push` 就停止重爬（欄位名稱沿用，見開發規格 7.2）。依上表每篇 24 小時內約重爬 60 次，Gossiping 一天數千篇會超出請求預算，門檻用來只追蹤有在發酵的文章（Gossiping 預設 10，其餘 0）。

### 4.3 管理後端（FastAPI）

#### API

| API | 用途 | 回應 |
|---|---|---|
| `GET /boards` | 列出看板設定（Scheduler 使用） | 200 |
| `POST /boards` | 新增看板 | 201；已存在 409；欄位不合法 422 |
| `PATCH /boards/{board}` | 調整頻率、門檻、啟用或停用（只更新有給的欄位） | 200；不存在 404；沒給欄位 422 |
| `POST /boards/{board}/crawl` | 手動觸發，直接寫入 `crawl.tasks`（列表任務，`reason=manual`） | 202；不存在 404；Kafka 失敗 503 |
| `GET /status` | 各看板 `last_changed_at`、近 24 小時新文章數，與 `dlq` 數量 | 200；Kafka 異常時 `dlq_count=-1` |

#### 規則

- 看板設定存在 PG 的 `boards` 表，FastAPI 是唯一入口；初始看板也透過 API 建立（`make seed`）
- `interval_sec` 下限 30 秒、`recrawl_min_push` 不可為負，看板名稱只允許英數、`_`、`-`
- 停用中的看板也允許手動觸發，方便正式啟用前測試
- `last_changed_at` 是「最後一次有變化」的時間，不是最後爬取時間：Ingest 只在內容有變化時寫入 `posts`，從 PG 拿不到真正的爬取時間
- `dlq` 數量為各 partition 的 high − low watermark 加總，約等於近 30 天（`dlq` 保留期）的數量
- CORS 允許的來源由 `API_CORS_ORIGINS` 設定，預設空白（不開放跨網域）；只允許 GET / POST / PATCH
- 沒有身分驗證，部署時只綁 `127.0.0.1`

### 4.4 Scheduler

實作：`src/radar/collector/scheduler.py`、`src/radar/collector/recrawl.py`

#### 設計

- 常駐程式，使用 APScheduler 3.x 的 `BlockingScheduler`（專案程式皆為同步，不需事件迴圈），**每個看板一個計時器**
- 每 30 秒向 `GET /boards` 同步設定，有變化才新增、移除或 `reschedule` 計時器
  - 新增的看板計時器會**立刻執行一次**，之後依 `interval_sec`（含 5 秒 jitter）
  - 停用、或已從 API 消失的看板 → 移除計時器
  - `interval_sec` 改變 → `reschedule`，從當下重新起算；要立刻爬就用手動觸發
- API 失敗（連線錯誤、非 200、格式錯誤）時維持現有計時器
- 派發失敗只記錄 ERROR，不讓計時器停掉，下一次觸發再送
- 計時器設定 `coalesce`、`max_instances=1`，前一次還沒做完就不會重疊執行

#### 計時器

| 計時器 | 頻率 | 動作 |
|---|---|---|
| `board:<name>` | 看板的 `interval_sec` | 派發列表頁任務（`reason=schedule`，key=board） |
| `sync_boards` | 30 秒（啟動時立刻執行） | 同步看板設定 |
| `due_posts` | 30 秒 | 派發到期的文章重爬任務（4.5） |
| `lock` | 30 秒 | 確認仍持有 advisory lock，失去就停止 |

#### 只能跑 1 個 instance

- 啟動時以 `pg_try_advisory_lock` 取得 PG session 層級的鎖，取不到就**待命**，每 10 秒重試；持有者停止（連線關閉）後由待命者接手
- `lock` 計時器檢查鎖仍屬於自己的連線；失去鎖就停止程式，由 `restart: unless-stopped` 重啟後重新取鎖
- 不放進 FastAPI 的 process，獨立部署

### 4.5 文章重爬排程

#### 查詢到期文章

```sql
SELECT p.post_id, p.board, p.url, p.created_at
FROM posts p
JOIN boards b USING (board)
LEFT JOIN crawl_state cs USING (post_id)
WHERE b.enabled                                          -- 停用的看板不重爬
  AND NOT p.is_deleted
  AND p.created_at > now() - interval '24 hours'
  AND (p.created_at > now() - interval '1 hour'          -- 1 小時內一律重爬
       OR p.comment_count >= b.recrawl_min_push)         -- 之後只追蹤推文總數（推＋噓＋→）達門檻的
  AND (cs.next_crawl_at IS NULL OR cs.next_crawl_at <= now())
ORDER BY cs.next_crawl_at NULLS FIRST, p.created_at DESC  -- 沒派發過的優先
LIMIT 500;                                               -- 其餘留到下一輪
```

- 先送出任務並 flush，成功後才依文章年齡算出新的 `next_crawl_at` 寫回 `crawl_state`：送出失敗就不推進排程，下一輪重試；寫入失敗只會重複派發，無害
- 超過 24 小時的文章把 `next_crawl_at` 設到一年後，不會再被查到
- 派發時就推進 `next_crawl_at`，不等爬蟲處理完：`crawl.tasks` 積壓超過重爬間隔時，同一篇會再派一次。Scheduler 拿不到爬取結果（Ingest 只在內容有變化時寫 PG），重複的任務由爬蟲略過（4.6）

#### 為什麼獨立成 `crawl_state` 表

`next_crawl_at` 放在 `posts` 的話，每次重爬都更新會產生 CDC 事件；不更新則排程不會推進。獨立成表並排除在 Debezium 監聽之外即可解決。

### 4.6 爬蟲

- 屬於同一個 consumer group，消費 `crawl.tasks`，結果寫入 `raw.posts` 與 `raw.html`（皆以 `post_id` 為 key）
- 不碰 PG、不讀設定
- 一次處理一個任務：一個列表任務可能牽動約 20 次請求，整批重試代價高
- **略過重複的重爬任務**：爬蟲以 LRU 記住 `post_id → 最後一次抓內頁的時間`；文章任務的 `created_at` 早於這個時間，代表派發之後已經抓過，不發請求直接略過
  - 文章任務的 key 是 `post_id`，同一篇固定由同一個爬蟲處理，記錄在本機就夠
  - 重啟或 rebalance 後清空，只會多抓幾次
- **速率限制**：每次請求間隔 2 秒 + 0～2 秒隨機，平均約 3 秒一次；3 個爬蟲合計約 1 次/秒
- **HTTP 回應**：
  - 200、404 正常處理；文章頁 404 視為被刪除，送出 `is_deleted=true` 的快照（推噓數為 0、沒有推文）
  - 429、5xx、逾時、連線錯誤 → 整批重試，不 commit；同一個網址連續 5 次仍失敗就略過（同 403），避免一篇卡住整個 partition
  - 其他狀態（403、3xx、Cloudflare 的 520／525）→ 記 WARNING 後略過，不重試；解析失敗記 ERROR（重抓結果相同，需要修 parser）
  - **略過之後誰補抓**：已在 PG 的文章由 Scheduler 的重爬補抓；列表任務裡的新文章還不在 PG，抓取失敗時**不記進列表快取**，下一輪列表輪詢會再抓，連續 3 輪都失敗才放棄並記 ERROR（這篇可能永久漏抓，#33）
  - 連續 20 次抓取失敗（PTT 或 Cloudflare 長時間無法連線）記一次 ERROR，恢復後記 INFO；單次失敗只記 WARNING，避免 Slack 被日常的 52x 淹沒
- 文章頁先送 `raw.html` 再解析，解析失敗時仍可在修好 parser 後重新解析
- 每批結束 flush producer，訊息落地後才 commit
- 每次請求帶 `over18=1` cookie；2026-10 實測 PTT 伺服器端已不擋未帶 cookie 的請求（只在瀏覽器以 JS 導向），parser 仍會對 `/ask/over18` 頁面拋錯以防恢復

---

## 5. Ingest：Kafka → PostgreSQL

### 5.1 寫入規則

- 消費 `raw.posts`，拆成文章與推文，在同一個 transaction 寫入
- 批次寫入（每 500 筆或每 1 秒）
- upsert 冪等，at-least-once 即可
- **同批去重**：同一個 `post_id` 只留 `crawled_at` 最新的一筆；`ON CONFLICT DO UPDATE` 不能在同一個語句更新同一列兩次
- **推文分段**：每 5000 列送一次，避開 PG 單一語句 65535 個參數的上限
- **刪除快照**：只把既有文章的 `is_deleted` 設為 true 並更新 `crawled_at`，保留刪除前的內容；從未見過的文章略過，已標記的不重複寫；比 `posts.crawled_at` 舊的刪除快照略過（較晚到的舊 404 不可蓋掉較新的 200）
- **推文同步**：推文以頁面上的順序編樓層，中間有推文被刪時後面全部往前移一層。快照不比 `posts.crawled_at` 舊時才同步（推文數也列入變化判斷，只多了箭頭時 `crawled_at` 同樣前進）：同一樓層內容不同就更新，超過新快照最大樓層的刪除；比較舊的快照不碰推文（否則晚到、推文較少的舊快照會刪掉新推文）。一般重爬只是新推文接在後面，舊樓層不變，不會多寫
- **撤銷刪除**：已標記刪除的文章收到比 `crawled_at` 新的正常快照時，`is_deleted` 改回 false 並寫入新內容，避免 PTT／Cloudflare 暫時性的錯誤 404 讓文章被永久誤判為刪除。Scheduler 照舊不重爬已刪除的文章；被誤判的文章若還在列表上，推文數一變（或爬蟲重啟、快取清空）列表任務就會重抓內頁而復原。真的被刪的文章在列表上沒有連結，不會被重抓
- **錯誤處理**：
  - DB 連線錯誤（`OperationalError`）→ 整批重試
  - 資料錯誤（`IntegrityError`、`DataError`，例如約束違反、文字含 `\x00`）→ rollback 後改成逐筆寫入（每筆一個 savepoint），寫不進去的送 `dlq`，其餘照常寫入並 commit；只在出錯時逐筆，平常仍整批寫入
  - 其他 DB 錯誤（例如 schema 與程式不一致）→ 中止服務，避免資料靜默遺失
  - 格式不合法的訊息由 consumer 送 `dlq`

### 5.2 帶條件的 upsert

```sql
INSERT INTO posts (post_id, board, author, title, content, url,
                   push_count, boo_count, comment_count, created_at, crawled_at)
VALUES (...)
ON CONFLICT (post_id) DO UPDATE SET
  push_count = EXCLUDED.push_count,
  boo_count  = EXCLUDED.boo_count,
  comment_count = EXCLUDED.comment_count,
  title      = EXCLUDED.title,
  content    = EXCLUDED.content,
  crawled_at = EXCLUDED.crawled_at,
  is_deleted = FALSE                                          -- 撤銷刪除
WHERE posts.crawled_at < EXCLUDED.crawled_at                  -- 舊快照不覆蓋新的
  AND (posts.is_deleted
    OR posts.push_count IS DISTINCT FROM EXCLUDED.push_count
    OR posts.boo_count  IS DISTINCT FROM EXCLUDED.boo_count
    OR posts.comment_count IS DISTINCT FROM EXCLUDED.comment_count  -- 只多了箭頭
    OR posts.title      IS DISTINCT FROM EXCLUDED.title       -- 作者可能改標題
    OR posts.content    IS DISTINCT FROM EXCLUDED.content);   -- 沒變化就不寫

-- 推文：只處理快照不比 posts.crawled_at 舊的文章
INSERT INTO comments (post_id, floor, type, user_id, content, commented_at)
VALUES (...)
ON CONFLICT (post_id, floor) DO UPDATE SET
  type = EXCLUDED.type, user_id = EXCLUDED.user_id,
  content = EXCLUDED.content, commented_at = EXCLUDED.commented_at
WHERE (comments.type, comments.user_id, comments.content, comments.commented_at)
  IS DISTINCT FROM
  (EXCLUDED.type, EXCLUDED.user_id, EXCLUDED.content, EXCLUDED.commented_at);

DELETE FROM comments
USING (VALUES (...)) AS v(post_id, max_floor)                 -- 新快照的最大樓層，沒推文為 0
WHERE comments.post_id = v.post_id AND comments.floor > v.max_floor;

-- 刪除快照
UPDATE posts SET is_deleted = TRUE, crawled_at = v.crawled_at
FROM (VALUES (...)) AS v(post_id, crawled_at)
WHERE posts.post_id = v.post_id
  AND NOT posts.is_deleted
  AND posts.crawled_at < v.crawled_at;
```

沒有變化就不寫入，也就不產生 CDC 事件。

### 5.3 Schema

實際定義以 `src/radar/common/db/models.py` 與 Alembic migration 為準；以下為對應的 DDL。

```sql
CREATE TABLE posts (
  post_id       TEXT PRIMARY KEY,               -- <board>.<PTT 檔名>
  board         TEXT NOT NULL,
  author        TEXT,                           -- 只存帳號，不含暱稱
  title         TEXT,
  content       TEXT,                           -- 不含標頭、推文、簽名檔
  url           TEXT NOT NULL,
  push_count    INT  NOT NULL DEFAULT 0,        -- 由推文計算
  boo_count     INT  NOT NULL DEFAULT 0,
  comment_count INT  NOT NULL DEFAULT 0,        -- 推＋噓＋箭頭
  created_at    TIMESTAMPTZ NOT NULL,
  crawled_at    TIMESTAMPTZ NOT NULL,
  is_deleted    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE comments (
  post_id       TEXT NOT NULL REFERENCES posts(post_id),
  floor         INT  NOT NULL,                  -- 從 1 開始，依頁面順序
  type          VARCHAR(8) NOT NULL CHECK (type IN ('push', 'boo', 'arrow')),
  user_id       TEXT,
  content       TEXT,
  commented_at  TIMESTAMPTZ,                    -- 推不出時間時為 NULL
  PRIMARY KEY (post_id, floor)
);

CREATE TABLE boards (
  board            TEXT PRIMARY KEY,
  enabled          BOOLEAN NOT NULL DEFAULT TRUE,
  interval_sec     INT NOT NULL CHECK (interval_sec >= 30),
  recrawl_min_push INT NOT NULL DEFAULT 0 CHECK (recrawl_min_push >= 0),  -- 4.2 重爬門檻（推文總數）
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()                     -- ORM 更新時刷新
);

CREATE TABLE crawl_state (
  post_id         TEXT PRIMARY KEY REFERENCES posts(post_id),
  next_crawl_at   TIMESTAMPTZ NOT NULL,
  last_dispatched TIMESTAMPTZ NOT NULL
);

CREATE INDEX ON posts (created_at);
CREATE INDEX ON crawl_state (next_crawl_at);
```

### 5.4 表的寫入者

| 表 | 寫入者 | Debezium 監聽 |
|---|---|---|
| `posts`、`comments` | Ingest consumer | ✅ |
| `boards` | FastAPI | ❌ |
| `crawl_state` | Scheduler | ❌ |
| `subscriptions`、`chat_settings`、`muted_posts` | Telegram bot | ❌ |

每張表只有一個寫入者。爬蟲不能同時寫 PG 和 Kafka（雙寫）。寫入者與是否被監聽也記在各表的 PG table comment。

- `comments.type` 用 CHECK 約束而非 PG 原生 enum，日後加值不必 `ALTER TYPE`
- 約束名稱依固定命名規則產生（例如 `ck_boards_interval_sec_min`），Alembic 才能穩定地修改

---

## 6. CDC 與 ClickHouse

### 6.1 Debezium

- `table.include.list` 只包含 `posts`、`comments`；publication `radar_cdc` 由 Alembic migration 建立，Debezium 不自動建立（`publication.autocreate.mode=disabled`）
- Avro 格式，schema 由 Apicurio 管理；Apicurio 使用同一個 PG instance 裡**獨立的 database** `apicurio`
- 開啟 `heartbeat.interval.ms`，避免冷門時段 replication slot 停滯、WAL 累積；broker 關閉了自動建立 topic，heartbeat topic 要列在 `topics.yaml`
- `ExtractNewRecordState` 攤平訊息，附加 `__op`、`__source_ts_ms`、`__source_lsn`；PG 端的刪除以 `delete.tombstone.handling.mode=rewrite` 改寫成 `__deleted=true`（與 PTT 刪文的 `is_deleted` 是兩回事）。`posts` 的列不會被刪；`comments` 在推文樓層位移時會被改寫或刪除（5.1），因此設 `REPLICA IDENTITY FULL`，刪除事件才帶完整的舊列（預設只帶主鍵，其他欄位是 null，ClickHouse 的非 Nullable 欄位會解析失敗）
- Converter 的 schema 快取：`fault-tolerant-refresh=true`、`check-period-ms` 拉長到 1 小時。預設每 30 秒過期，過期後下一筆訊息就要同步向 Apicurio 註冊 schema，任何一次失敗都會讓 task 永久停止（6.4）
- 版本：Debezium 3.7.0.Final（`quay.io/debezium/connect`，Docker Hub 的 `debezium/connect` 已停止更新）、Apicurio Registry 3.3.3

### 6.2 ClickHouse 讀取 Avro 的方式（S2-01 驗證結果）

> 2026-10-07 實測。先以 Debezium 2.5 + Apicurio 2.5.10 + ClickHouse 25.8 驗證可行，再改用目前版本 Debezium 3.7 + Apicurio 3.3.3 + ClickHouse 26.8（皆搭配 Kafka 4.1）重新驗證；以下以目前版本為準

ClickHouse 的 `AvroConfluent` 格式能直接讀 Apicurio 序列化的訊息，不需要中間的 Python consumer。條件：

| 項目 | 設定 | 不這樣做的後果 |
|---|---|---|
| 訊息格式 | schema ID 放在訊息開頭（1 byte magic + 4 bytes ID）；Apicurio 3.x converter 預設即是（`Default4ByteIdHandler`），2.x 需設 `as-confluent=true`、`headers.enabled=false` | ID 放在 Kafka header，ClickHouse 讀不到 |
| ID 種類 | converter 明確設 `use-id=contentId`（3.x 預設即是，寫明避免日後預設值改變） | ccompat API 用 contentId 查 schema；寫成 globalId 時，「內容和既有 schema 相同的新版本」查詢得到 404，整個 topic 卡住（2.x 實測） |
| Registry 位址 | `format_avro_schema_registry_url = http://apicurio:8080/apis/ccompat/v7` | — |
| 缺欄位 | `input_format_avro_allow_missing_fields = 1` | Kafka engine 表的欄位在訊息的 schema 中不存在（例如新增欄位前產生的舊訊息）時，整個 topic 卡住（實測） |
| 時間欄位 | Debezium 把 `timestamptz` 轉成 ISO 8601 字串（`ZonedTimestamp`）；Kafka engine 表宣告為 `String`，在 materialized view 用 `parseDateTime64BestEffort` 轉換 | 直接宣告 `DateTime64` 會解析失敗，訊息卡住 |

- 以上 ClickHouse 設定集中在 named collection `cdc_kafka`（`infra/clickhouse/config.d/`），DDL 只寫 topic 與 consumer group；使用者需要 `named_collection_control` 權限（`infra/clickhouse/users.d/`）
- Debezium 3.x 已移除 `delete.handling.mode`、`drop.tombstones`，舊設定會被忽略且不報錯（實測時 `__deleted` 因此消失）
- snapshot 的列 `__op=r`，同一次 snapshot 的列共用同一個 LSN
- ClickHouse 重啟後，Kafka engine 要等舊成員的 session 逾時才重新分配 partition，約 1 分鐘內不會消費

### 6.3 ClickHouse 表

使用 Kafka table engine + materialized view 直接消費 topic。

| 表 | Engine | 來源 | 用途 |
|---|---|---|---|
| `posts_latest` | `ReplacingMergeTree(lsn)` | `cdc.public.posts` | 最新狀態 |
| `posts_history` | `MergeTree` | `cdc.public.posts` | 推噓數變化歷程 |
| `comments_latest` | `ReplacingMergeTree(lsn, is_deleted)` | `cdc.public.comments` | 每分鐘新增推文數；多一個 `board` 欄位（從 `post_id` 取出，PG 的 `comments` 沒有），依看板統計時不必 join；PG 端的改寫、刪除以 LSN 取代，`is_deleted` 來自 `__deleted`，查詢加 `FINAL` 才會去掉已刪除的列 |
| `labels` | `MergeTree` | `labels` | 標註結果；一則訊息的 `sentiments` 以 `ARRAY JOIN` 攤成一列一個 (target, polarity)（15.3） |
| `predictions` | `MergeTree` | `predictions` | 推論結果（含 `model_version`） |
| `predictions_shadow` | `MergeTree` | `predictions.shadow` | shadow 推論結果，結構同 `predictions`；只供模型比較，呈現層不讀（8.4） |
| `alerts` | `MergeTree` | `alerts` | 警示紀錄 |
| `post_votes`（view） | 一般 view | `comments_latest` | 每篇文章的 `post_id`、`board`、`push`、`boo`、`arrow`（`FINAL`、不含已刪除推文）；dashboard 用（開發規格 7.25） |
| `post_sentiment_latest`（view） | 一般 view | `predictions` | 每篇最新一筆推論的 `post_id`、`model_version`、`polarity`、`score`（三類最高分，`argMax(…, predicted_at)`）；沒有推論的文章不出現 |

- `posts_latest` 的 version 用 `__source_lsn`：同一列的後續變更 LSN 一定較大；`ts_ms` 是毫秒，同一毫秒內多次變更會分不出先後
- 查詢 `posts_latest`、`comments_latest` 加 `FINAL` 或用 `argMax`
- PTT 刪文以 `is_deleted` 處理；撤銷刪除只是 `is_deleted` 改回 false 的一般更新，`posts_latest` 以較大的 LSN 取代即可
- JSON topic 同樣用 named collection（`json_kafka`），並設 `input_format_skip_unknown_fields=1`：訊息只做加欄位的相容變更（開發規格 2.2），新欄位不會讓 ClickHouse 卡住
- ClickHouse 的 schema 以 `infra/clickhouse/migrations/` 的編號 SQL 檔管理，已合併的檔案不可修改（同 Alembic）

### 6.4 故障處理

Kafka Connect 的 task 遇到非 `RetriableException` 的錯誤就進入 `FAILED`，不會自動恢復，要手動重啟。這時爬蟲與 Ingest 照常運作，所以 consumer lag、DLQ 都看不出異常；但 ClickHouse 會停止更新，replication slot 沒人讀，PG 的 WAL 持續累積（2026-10-10 驗收時發生，約 70 MB/小時，#31）。

分三層處理：

| 層 | 作法 | 處理的情況 |
|---|---|---|
| 減少失敗 | Converter 快取設定（6.1） | 快取過期後，向 Apicurio 刷新時偶發的連線錯誤 |
| 自動恢復 | 常駐服務 `cdc-watchdog` 定期查 connector 狀態，`FAILED` 時呼叫 Connect REST API 重啟失敗的 task，間隔以指數退避拉長 | 其他原因造成的 task 失敗（例如 Apicurio 停機期間遇到新的 schema） |
| 讓人知道 | `cdc-watchdog` 同時檢查 replication slot：`active=false` 持續太久，或 WAL 延遲超過門檻，就記 ERROR，由 loggerhelper 送到 Slack | 自動恢復失敗、PG 端的問題 |
| 監看 watchdog 本身 | `cdc-watchdog` 每輪 ping 外部的 heartbeat 服務（healthchecks.io）；CDC 異常時改 ping `/fail`。外部服務超過期限沒收到 ping，或收到 `/fail`，就寄 email | watchdog crash、卡住、開發機睡眠或 Docker 停止；Slack 漏看 |

- **為什麼要外部服務**：監控程式和被監控的服務在同一台機器上，無法回報「整台機器停了」（2026-10-10 的驗收監控腳本就是無聲無息地停了 10 小時）；只有「該收到卻沒收到就通知」的外部服務能涵蓋這種情況
- **heartbeat 只帶 URL，不送任何資料內容**；沒設定 URL 就不送（測試與 e2e 環境都不設）

- **不用 Connect 內建的錯誤處理**：`errors.retry.timeout` 只重試 `RetriableException`；`errors.tolerance=all` 會丟掉訊息，資料不完整
- **不設 `max_slot_wal_keep_size`**：超過上限時 PG 會讓 slot 失效，必須重新 snapshot；寧可記 ERROR 讓人處理
- **重啟後會重送**：Debezium 從最後一次 flush 的 offset 接續，之後的事件會再送一次。`posts_latest`、`comments_latest` 以 LSN 去重不受影響；`posts_history` 是 `MergeTree`，會出現 `(post_id, lsn)` 相同的重複列，畫曲線時要以 LSN 去重
- `cdc-watchdog` 只讀 PG 的系統表，不寫入任何表（5.4）

---

## 7. 離線 ML

### 7.1 分工

| 任務 | 工具 |
|---|---|
| 情緒分類 | 自己訓練的小模型 |
| 實體辨識 | CKIP Transformers |
| 去重 / 轉載偵測 | SimHash、MinHash |
| 主題聚類 | embedding + BERTopic |
| 熱度異常偵測 | z-score、EWMA |
| 標註訓練資料 | LLM |
| 熱門話題摘要 | LLM |

### 7.2 不直接用現成模型的原因

- 現成中文情緒模型多以簡體電商評論訓練，與 PTT 有 domain shift
- PTT 的反串、酸文，字面與實際情緒相反
- Aspect-based：同一句話對不同對象的情緒不同

### 7.3 標註策略

1. 推噓比作為弱標註，先驗證相關性
2. LLM 標註 3,000～5,000 篇（情緒 + 對象）
3. 兩個模型交叉標註，不一致的人工檢查
4. 保留人工測試集，只用於評估

標註 consumer 從 `cdc.public.posts` 抽樣（約 5%），寫入 `labels`，附 `labeler` 與 `version`。**不可寫回 `posts` 表**（會觸發 CDC 迴圈）。

### 7.4 標註成本

- 每篇約 700～1,000 input tokens，5,000 篇約 3～5M tokens（一次性）

| 方案 | 成本 | 備註 |
|---|---|---|
| Gemini Flash 免費額度 | $0 | 首選，需自行限速 |
| 便宜付費 API | 數美元 | 可搭配 Batch API |
| Ollama 本地 | $0 | 只用於測試 prompt；7B 模型判斷反串較弱 |

- LLM 只用在**標註**（離線批次 + 串流抽樣 5%），線上預測一律用自己訓練的小模型：LLM 的額度、延遲、成本都撐不住每篇文章推論
- 多組 API key 輪替暫不做；需要時只換不同服務商（開發規格 7.11）

### 7.5 模型路線

1. Baseline：TF-IDF + Logistic Regression
2. 進階：fine-tune 中文 BERT（Kaggle / Colab 免費 GPU 訓練，CPU 推論）：agent 準備 notebook，甲方執行並交回模型包（D-019）；模型包格式與流程見開發規格 7.27
3. 比較兩版與 LLM 標註的準確率、成本

### 7.6 訓練頻率

手動或每週一次，訓練資料從 ClickHouse 匯出（`posts_latest` join `labels`）。

---

## 8. 線上串流處理

### 8.1 工具選擇

| 任務 | 性質 | 工具 |
|---|---|---|
| 情緒推論 | 無狀態 | Python Kafka consumer |
| 熱度偵測 | 有狀態視窗聚合 | Quix Streams |
| 每日摘要 | 批次 | Telegram bot 內的定時工作 |

### 8.2 情緒推論

- 消費 `cdc.public.posts`，載入模型預測，寫入 `predictions`
- 訊息帶 `model_version`；啟動時載入一個指定的模型版本（`models/<model_version>/`），換模型就重啟服務
- **避免重複推論**：大部分 CDC 事件只是推噓數更新。以模型輸入文字（標題＋截斷後的內文，與訓練相同）的 hash 判斷，與本地快取的 hash 相同就不推論
  - 快取裡沒有這篇時：新文章（`op=c`）推論；更新（`op=u`）與 snapshot（`op=r`）只記下 hash、不推論。重啟後快取是空的，若對更新也推論，每篇文章的第一次推噓數變化都會重複推論一次
  - 重啟時從 ClickHouse `predictions` 載入同一個模型版本每篇最新的 `text_hash`，重啟後編輯的文章照常重新推論（開發規格 7.19）；只有重啟前幾秒、還沒寫進 ClickHouse 的推論載不到
  - 服務上線前已存在的文章沒有推論結果，需要時另外補跑
  - Connect 重啟重送的 `op=c` 事件，hash 相同也不會重複推論
- 刪除的文章（`is_deleted`）不推論
- 模型檔不進 image：compose 以唯讀方式掛載 `models/`，模型版本由環境變數指定
- 模型格式由 `model_card.json` 的 `kind` 區分（baseline 為 sklearn，BERT 為 ONNX），推論與評估經同一個 `Classifier` 介面載入（開發規格 7.27）
- **呈現**：Telegram（警示、熱門、看板概況，9.2）與 Dashboard（9.1）讀 ClickHouse `predictions` 每篇最新一筆；信心不足顯示「不確定」（15.8）

### 8.3 熱度偵測

- 輸入：`cdc.public.comments`、`cdc.public.posts`；`comments` 的事件除了新增（`c`）也有改寫（`u`）、刪除（`d`），計算新增推文數時只算 `c`
- 依文章 / 看板做滑動視窗統計（每 1 分鐘、視窗 10 分鐘），之後擴充到實體、主題（見 15.2）
- 與歷史基準比較（z-score / EWMA），超過門檻寫入 `alerts`；每分鐘結算時判斷，警示的推文數反映結算時的熱度，不是剛越過門檻的值
- 文章與「該看板活躍文章共用的基準」比較，基準每分鐘更新一次，冷卻中的文章不納入；文章另設較高的最低推文數（80，看板 30），因為大多數文章的推文很少，z-score 對文章幾乎沒有篩選力（開發規格 7.20）
- Quix Streams：純 Python、狀態存 RocksDB 並備份到 changelog topic；以 exactly-once 處理，重啟後不重送已發過的警示
- 以看板為 key 分組，文章與看板兩種單位在同一份 state 計算（文章要和看板的基準比較）
- 時間基準用觀測時間（推文進 PG 的時間），寬限 2 分鐘：推文要等爬蟲抓到才看得到，進 PG 時已晚約 8 分鐘，用推文時間會把大部分推文當成遲到丟掉（開發規格 7.20）
- 推文時間比觀測時間早超過 30 分鐘的不計入（補抓、舊爆文）；比當下早超過 1 小時的舊事件只更新基準、不觸發
- 細節見開發規格 7.20；回放與人工暴增工具 `streaming/replay.py`

### 8.4 Shadow 比較

- 新版模型由另一個推論服務（`inference-shadow`）執行，使用新的 consumer group（每個模型版本一個），與舊版並行
- shadow 寫到 `predictions.shadow` → ClickHouse `predictions_shadow`，不寫 `predictions`：呈現層取每篇最新一筆時不分版本，shadow 結果混進去會改變使用者看到的情緒
- 兩表以 `model_version` 區分，在 ClickHouse 比較一致率、不一致的文章、推論延遲與信心分布；人工測試集的分數離線評估（開發規格 7.27）
- 切換預設模型只改現行推論服務的模型版本，呈現層不必改

---

## 9. 呈現層

### 9.1 Dashboard

Grafana 接 ClickHouse（開發規格階段 7）：各看板推文量曲線、情緒分布與趨勢、爭議度、近 24 小時警示、熱門文章排行。長時間的趨勢看 Dashboard；即時通知與快速查詢在 Telegram。

- 呈現方式已定案：全用 Grafana 面板，自建 web 前端延到階段 9（D-014）；設計見開發規格 7.25
- 唯讀：Grafana 以專用的 ClickHouse 唯讀帳號查詢，只綁本機並需登入

### 9.2 Telegram bot

主要介面。MVP（階段 5）只有文字指令；階段 6 改成按鈕選單（15.7），文字指令保留。

- **推送**：消費 `alerts`，依訂閱（看板）推送。每則警示附：
  - 熱度：視窗內推文數，與平常（基準）的倍數
  - 推、噓、箭頭數與爭議度（噓 ÷（推＋噓））
  - 文章情緒：模型推論的標籤與信心；信心不足顯示「不確定」，還沒推論的顯示「尚無」（15.8）
  - 按鈕：開啟原文（URL 按鈕）、看板概況、這篇不再通知、訂閱設定
  - 看板警示另附推文最多的前 3 篇，各帶推噓與情緒
- **主選單**（`/start`、`/menu`）：按鈕切換時編輯同一則訊息，不洗版
  - 🔥 現在熱門：最近 60 分鐘推文最多的文章（預設只看訂閱的看板），附推噓、爭議度、情緒與原文按鈕
  - 📋 我的訂閱：列出所有啟用的看板，✅／⬜ 點一下切換
  - 📈 看板概況：選看板後顯示近 24 小時的文章數、推文量、情緒比例（負面／中立／正面）、爭議度最高的文章、今天的警示數
  - ⚙️ 通知設定：文章警示、看板警示分別開關；「不再通知」的文章清單（可恢復）
- 使用 long polling，不需要對外開放 HTTP；以 `httpx2` 直接呼叫 Bot API（含 inline keyboard、callback query），不加 SDK
- 只回應允許清單內的 chat（`TELEGRAM_ALLOWED_CHAT_IDS`），按鈕回呼同樣檢查；清單沒設就啟動失敗，要開放所有人須明確設 `TELEGRAM_ALLOW_ALL=true`（D-010，細節見開發規格 7.21）
- 之後：`/subscribe 台積電`（實體，15.2 進階 1）；Mini App（14.3，上雲、有 HTTPS 之後）
- 細節見開發規格 7.21（MVP 文字指令）、7.23（按鈕選單與情緒呈現）
- 每日摘要：APScheduler cron trigger，每天 08:00 用 LLM 摘要前一天的熱門話題（S5-08，非 MVP）

---

## 10. 程式結構與部署

### 10.1 資料夾結構

```
<repo>/
├── src/radar/               # 所有 Python 程式碼，import 路徑為 radar.*
│   ├── common/              # 設定、log、ORM model、Kafka 訊息格式、Kafka client、topic 管理
│   ├── api/                 # [常駐 ×1] FastAPI（main、routes、repository、seed）
│   ├── collector/
│   │   ├── scheduler.py     # [常駐 ×1] APScheduler
│   │   ├── crawler.py       # [常駐 ×N]（http、list_cache）
│   │   └── parsers/         # PTT 列表頁與文章頁解析
│   ├── ingest/              # [常駐] main、writer
│   ├── cdc/watchdog.py      # [常駐 ×1] 監看 Debezium connector 與 replication slot
│   ├── ml/
│   │   ├── labeling/
│   │   │   ├── prompt.py    # 標註準則（RULES）與輸出格式，對應 docs/labeling-guideline.md
│   │   │   ├── llm.py       # Labeler：Gemini、OpenAI 相容（Groq、OpenRouter）、FallbackLabeler
│   │   │   ├── stream.py    # [常駐] 抽樣標註
│   │   │   ├── backfill.py  # [一次性] 初期批次標註
│   │   │   ├── manual.py    # [一次性] Claude 手動標註的匯出／匯入（搭配 skill /label-posts）
│   │   │   ├── cross_check.py  # [一次性] 兩個標註者交叉比對
│   │   │   ├── testset.py   # [一次性] 人工測試集
│   │   │   └── human_app.py # [本機] 人工標註頁
│   │   ├── experiments/     # [一次性] push_ratio（推噓比弱標註實驗）
│   │   ├── training/        # [一次性] export / train / evaluate / import_model / compare；classifier（sklearn、ONNX 共用介面）
│   │   └── inference/main.py  # [常駐]
│   ├── streaming/
│   │   ├── heat.py          # [常駐] Quix Streams
│   │   └── replay.py        # [一次性] 錄製、回放、人工暴增
│   └── bot/                 # [常駐] Telegram bot：main（long polling、推送）、views（訊息與按鈕）、callbacks、stats（ClickHouse 查詢）
├── notebooks/               # 甲方在 Colab／Kaggle 執行的 BERT fine-tune notebook（開發規格 7.27）
├── infra/
│   ├── docker-compose.yaml
│   ├── debezium/
│   ├── postgres/
│   ├── clickhouse/
│   └── terraform/
└── Dockerfile
```

### 10.2 程式類型

| 類型 | 程式 | 執行方式 |
|---|---|---|
| 常駐 | api、scheduler、crawler、ingest、cdc/watchdog、labeling/stream、inference（含 shadow）、heat、bot | docker-compose service |
| 一次性 | labeling/backfill、manual、cross_check、testset、experiments/*、training/*、inference/backfill_hash、streaming/replay | 手動執行 |
| Colab／Kaggle | `notebooks/bert_finetune.ipynb` | 甲方在 GPU 平台執行，交回模型包（D-019） |
| 本機 | labeling/human_app | 人工標註時執行，只綁 127.0.0.1 |

不使用系統 cron，定時行為都在常駐程式內用 APScheduler 處理。

### 10.3 docker-compose

`infra/docker-compose.yaml`；所有自寫服務共用一個 image（`radar-app`），只有 `command` 不同。

| 服務 | profile | 說明 |
|---|---|---|
| `kafka_1`～`kafka_3`、`postgres` | （預設） | 本機開發時服務直接用 `uv run` 執行 |
| `apicurio-db-init`、`apicurio`、`connect`、`clickhouse` | （預設） | 階段 2 起屬於資料流的一部分，`make up` 一併啟動；`apicurio-db-init` 是一次性服務 |
| `label-stream` | `labeling` | 串流抽樣標註，會持續呼叫 LLM API，`make up-labeling` 才啟動 |
| `inference` | `inference` | 情緒推論（8.2），需要先訓練好模型；`make up-inference` 才啟動，以唯讀方式掛載 `models/` |
| `inference-shadow` | `shadow` | shadow 推論（8.4），模型版本與現行不同；`make up-shadow` 才啟動，比較結束就停 |
| `heat`、`bot` | `alerting` | 熱度偵測（8.3）與 Telegram bot（9.2）；bot 需要 `TELEGRAM_BOT_TOKEN`，`make up-alerting` 才啟動；heat 的 RocksDB 掛 volume `heat_state` |
| `grafana` | （預設） | Dashboard（開發規格 7.25）：只綁 `127.0.0.1:${GRAFANA_PORT}`、需登入，以唯讀帳號查 ClickHouse；`infra/grafana/Dockerfile` 建置時裝好 ClickHouse plugin，datasource 與 dashboard 以 provisioning 載入，資料放 volume `grafana_data` |
| `kafka-ui` | （預設） | 開發期間預設啟動（http://localhost:8089，只綁本機），部署前移除（S9-06） |
| `init` | `app` | 一次性：Alembic、建立 topic、ClickHouse migration、註冊 connector（皆冪等）；唯一負責建置 `radar-app` image 的服務 |
| `api` | `app` | 只綁 `127.0.0.1:8000` |
| `scheduler` | `app` | 只能 1 個；多開時其餘的待命 |
| `crawler` | `app` | `replicas: 3` |
| `ingest` | `app` | |
| `cdc-watchdog` | `app` | 只能 1 個；多開會重複重啟 connector（6.4） |

- `make up-app` 啟動整套；自寫服務等 `init` 成功結束後才啟動
- 端到端測試另加 `infra/docker-compose.e2e.yaml`：假 PTT 伺服器、爬蟲改打它、重爬間隔縮短，並改用 e2e 專用的資料與 log volume（`e2e_app_logs`），不碰開發資料；`make e2e-down` 的 `down -v` 只會刪到 e2e 專用的 volume（#29）
- 所有服務 `restart: unless-stopped`（`init` 除外）

### 10.4 上雲

- 不用託管 Kafka（太貴）
- Terraform 開一台 VM（例如 Oracle Cloud 免費 ARM），VM 上跑 docker-compose

---

## 11. 資源估算

### 11.1 記憶體

| 服務 | 占用 |
|---|---|
| Kafka（KRaft，3 節點） | ~1～1.5GB（實測閒置約 0.9GB） |
| Kafka Connect + Debezium | ~1GB（spike 實測約 0.7GB） |
| Apicurio | ~0.5GB（spike 實測約 0.3GB） |
| ClickHouse | ~1GB+（spike 實測閒置約 0.3GB，26.8 版） |
| PostgreSQL | ~0.3GB |
| Kafka UI | ~0.3GB |
| Grafana | ~0.1～0.2GB |
| 自寫 Python 服務 | ~1～1.5GB |
| shadow 推論（BERT，階段 8 比較期間） | 待調查（開發規格 7.27「需調查」） |
| **合計** | **約 6～7GB** |

### 11.2 吞吐量

每秒個位數到數百筆事件，不是瓶頸。

### 11.3 減輕負擔

- JVM 服務設定 heap 上限
- Kafka UI 部署時移除（S9-06）
- 標註用雲端 API，不同時跑 Ollama

---

## 12. 常見陷阱

### 12.1 資料流

- [ ] 爬蟲同時寫 PG 和 Kafka（雙寫）
- [ ] 標註結果寫回 `posts` → CDC 迴圈
- [ ] `raw.posts` 沒用 `post_id` 當 key → 順序錯亂
- [ ] 一個看板開一個 topic
- [ ] 用 `board` 當 partition key → 負載不均

### 12.2 PostgreSQL 與 CDC

- [ ] `next_crawl_at` 放在 `posts` 表
- [ ] upsert 沒比較 `crawled_at` → 舊快照覆蓋新資料
- [ ] `crawled_at` 列入變化判斷 → 每次重爬都產生事件
- [ ] 同一批有重複的 `post_id` 沒先去重 → `ON CONFLICT DO UPDATE` 直接報錯
- [ ] 刪除快照直接 upsert → 推噓數被清成 0、內文被清空
- [ ] 刪除標記不可逆、不比較 `crawled_at` → 暫時性的 404 或晚到的舊 404 讓文章被永久誤判為刪除
- [ ] 一次 INSERT 太多推文 → 超過 PG 65535 個參數上限
- [ ] 推文只新增不同步 → 中間的推文被刪後樓層位移，`comments` 與頁面、推噓數對不上
- [ ] 變化判斷只看推噓數 → 只多了箭頭時 `crawled_at` 不前進，晚到的舊快照刪掉較新的推文
- [ ] 會被刪除的表沒設 `REPLICA IDENTITY FULL` → Debezium 刪除事件只帶主鍵，下游的非 Nullable 欄位解析失敗
- [ ] Debezium 沒開 heartbeat → WAL 塞滿硬碟
- [ ] Connect task `FAILED` 沒人重啟、只看 consumer lag → CDC 停了好幾個小時都沒發現，WAL 持續累積
- [ ] Apicurio converter 用預設的快取設定 → 每 30 秒同步刷新一次 schema，一次連線失敗就讓 task 永久停止
- [ ] ClickHouse 用一般 MergeTree 存最新狀態 → 重複列

### 12.3 排程

- [ ] 爬蟲自己讀設定 → 重複爬
- [ ] Scheduler 多個 instance 或放進 FastAPI → 重複派發
- [ ] Scheduler 拿不到設定就停止 → API 一掛資料流就斷
- [ ] 端到端測試與開發共用資料庫 → Scheduler 對真實文章派發重爬，假伺服器回 404 被誤標為刪除
- [ ] 服務比 topic 先啟動 → 派發逾時、consumer 訂閱不到 topic（由 `init` 先建好）
- [ ] 看板頻率沒有下限 → IP 被封鎖
- [ ] 每篇文章都依年齡重爬 → Gossiping 的請求量超出預算（用 `recrawl_min_push` 門檻）
- [ ] 積壓時同一篇被重複派發，每個重複任務都發請求 → 積壓自我放大（爬蟲略過派發後已抓過的文章，4.6）
- [ ] 抓取失敗的新文章也記進列表快取 → 推文數沒變就不再抓，又還不在 PG、沒有重爬，永久漏抓（4.6）

### 12.4 ML 與資源

- [ ] 每篇都送 LLM → 額度撐不住
- [ ] 訓練與評估用同一份資料 → 分數虛高
- [ ] JVM 沒設 heap 上限 → 記憶體爆掉

---

## 13. 實作順序

| 階段 | 內容 | 成果 |
|---|---|---|
| 1 | FastAPI + Scheduler + 爬蟲 + Ingest + PG | 透過 API 管理看板，資料持續流入 PG |
| 2 | Debezium + Apicurio + ClickHouse | ClickHouse 看得到推噓數變化 |
| 3 | LLM 標註 + TF-IDF baseline | 第一版模型與評估分數 |
| 4 | 推論 consumer | 新文章自動帶情緒分數 |
| 5 | 熱度偵測 + Telegram bot | 話題暴增時收到通知（**MVP**） |
| 6 | Telegram 互動與情緒呈現 | 按鈕操作；警示帶推噓、爭議度與文章情緒 |
| 7 | Dashboard | 視覺化 |
| 8 | BERT + shadow 比較 | 模型比較報告 |
| 9 | Terraform 上雲 | 24 小時運作 |

之後的階段（實體與主題熱度、即時資料來源、推文層級情緒、Mini App 等）見開發規格「後續階段」。

---

## 14. 延伸功能

### 14.1 Flink

把熱度偵測從 Quix Streams 換成 Flink。

- 適用時機：需要 event time / watermark、多串流 join（例如與股價 join）、exactly-once、處理量超過單一 process
- 代價：記憶體多 1～2GB，部署與除錯更複雜
- 遷移：視窗邏輯改寫成 Flink SQL 的 `TUMBLE` / `HOP`，topic 不變，可並行比對

### 14.2 看板設定改用 Kafka 推送

- FastAPI 修改設定時寫入 compacted topic `config.boards`，Scheduler 改為消費該 topic
- 優點：設定立即生效，可練習 log compaction
- 代價：需處理雙寫（Outbox pattern 或 Debezium 監聽 `boards`）

### 14.3 Telegram Mini App

- 在 Telegram 裡開網頁介面：圖表、可篩選的清單、看板情緒趨勢
- 前置：對外的 HTTPS 網址（上雲後，開發規格階段 9）；後端要驗證 Telegram 傳來的 `initData` 簽章
- 與 Dashboard 有重疊：Mini App 給使用者在手機上看，Grafana 給維運與分析

### 14.4 推文層級的情緒（群眾反應）

- 現在的模型判斷「文章本身的情緒」（作者的立場）；輿情更關心讀者的反應
- 推噓只代表同不同意（15.6），不是情緒；要知道讀者在支持、反對還是嘲諷，需要對推文內容分類
- 做法：LLM 抽樣標註推文 → 訓練推文層級的模型 → 彙總成「這篇底下的輿論偏向」，呈現在 Telegram 與 Dashboard
- 代價：另一筆標註費用；推文短、反諷多，難度比文章高
- 時程未定，等階段 6 上線看實際需求再決定（開發規格「後續階段」）

---

## 15. 已決定事項

> 決定日期：2026-10-06

### 15.1 第一批追蹤看板

`Gossiping`（八卦，需 `over18` cookie）、`Stock`、`Tech_Job`。

### 15.2 熱度偵測的單位：分階段，最終以主題為主

| 階段 | 單位 | 做法 | 時機 |
|---|---|---|---|
| MVP | 文章 + 看板 | 單篇文章推文速度、看板整體推文量，與該看板歷史基準比較 | 實作順序第 5 階段 |
| 進階 1 | 實體 | CKIP NER + 自訂詞典（如「台積電」），跨文章彙總 | MVP 之後 |
| 進階 2 | 主題 | 離線 BERTopic 定期 fit，線上用 embedding 指派到最近的主題 | 有足夠歷史資料後 |

- 理由：主題聚類需要離線 fit、主題 ID 在重新 fit 後會變，不適合當 MVP；文章級訊號在 PTT 上最直接（一篇文正在變爆文）
- `alerts` 訊息一開始就用 `unit_type`（`post` / `board` / `entity` / `topic`）+ `unit_key`，之後擴充不需改 schema

### 15.3 情緒標籤：先三分類，schema 預留 aspect-based

- 情緒極性用 enum：`positive` / `negative` / `neutral`
- 對象（target）**不是 enum**，是開放的實體字串；以「一列一個 (target, polarity)」存放，`target IS NULL` 代表整篇
- 模型 MVP 只訓練整篇三分類；但 LLM 標註那 3,000～5,000 篇時**同時輸出對象與各自情緒**，之後做 aspect-based 不必重標

```json
{"post_id": "...", "labeler": "gemini-flash", "version": "v1",
 "sentiments": [
   {"target": null,     "polarity": "negative"},
   {"target": "台積電", "polarity": "positive"}
 ]}
```

### 15.4 保留原始 HTML，存在 Kafka

- 新增獨立 topic `raw.html`（key = `post_id`），不塞進 `raw.posts`，讓 Ingest 不必讀大訊息
- 用途：parser 有 bug 時可以重新解析
- 設定：`compression.type=zstd`、`max.message.bytes` 調到 5MB（爆文 HTML 可能超過預設 1MB）、保留 3 天
- 粗估：Gossiping 重爬頻繁，未壓縮可能每天 10GB 以上，zstd 壓縮後約 1/5～1/10
- 需要長期封存時再考慮 MinIO（自架、相容 S3 API 的物件儲存）

### 15.5 不拆出 `raw.comments`

- 文章與推文維持在同一則 `raw.posts` 訊息
- 理由：`comments` 有 FK 指向 `posts`，拆成兩個 topic 後到達順序無法保證，可能先到推文、找不到文章；同一個 transaction 寫入也會失效
- 下游本來就從 `cdc.public.comments` 拿到逐筆推文，不需要在 raw 層拆
- 單則訊息過大時的對策：zstd 壓縮、調高 `max.message.bytes`；仍不夠再讓爬蟲只送新樓層（任務帶 `last_floor`）

### 15.6 推噓比作為弱標註：已驗證，不採用（S3-05）

- 疑慮：推噓代表「同不同意這篇文」，不等於「這篇文的情緒」（例如痛罵某公司的文章被大量推）
- 結果（`docs/reports/s3-05-push-ratio.md`）：Groq、Claude、人工三種標註來源，各情緒類別的推噓比中位數都在 0.87～0.91，相關係數接近 0 → **不當標籤**
- **改當獨立指標**，直接呈現給使用者（9.2、9.1）：共鳴度（推文總數）、爭議度（噓 ÷（推＋噓））、箭頭比例
- **不當模型特徵**：與情緒沒有相關；推噓數持續變動，當特徵會讓同一篇的預測跳動，每次推噓變化都要重新推論（與 8.2「推噓更新不重新推論」衝突），訓練與推論時的數值也不一致
- 推文層級的 `推` / `噓` 對「該則推文對文章的態度」可能是較好的弱標註：需要推文層級的情緒標註才能驗證，併入 14.4

### 15.7 Telegram 互動：按鈕選單，之後再做 Mini App（2026-10-17）

- MVP 的文字指令要記看板名稱與參數（`/subscribe Gossiping`），不符合 Telegram bot 的使用習慣
- 採 inline keyboard：long polling 就能用、不需要對外網址、不用另寫前端；按鈕切換時編輯同一則訊息
- Mini App（14.3）的畫面更豐富，但需要 HTTPS 與另一套前端，等上雲後再做
- 文字指令保留（相容、除錯用）

### 15.8 情緒呈現的原則（2026-10-17）

- 「情緒」目前指文章本身的情緒；群眾反應見 14.4。介面上寫「文章情緒」，避免使用者誤會成推文的風向
- 單篇顯示時附信心，低於門檻顯示「不確定」：baseline macro-F1 0.504，positive 幾乎分不出來（`docs/reports/model-evaluation.md`）
- 看板層級看比例與趨勢，比單篇判斷可靠
- 換成 BERT（階段 8）後重新決定門檻
