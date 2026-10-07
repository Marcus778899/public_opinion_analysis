# 即時輿情雷達：設計草案

> 狀態：實作中（階段 0 完成，階段 1 進行中；進度見開發規格第 6 章）
> 最後更新：2026-10-07
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

追蹤 PTT 等社群上的話題，在討論**開始發酵的前幾分鐘**偵測並通知使用者，同時提供情緒分析與話題摘要。

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
| Apicurio | 1 | Schema Registry |
| ClickHouse | 1 | OLAP 分析、熱度曲線、訓練資料來源 |
| Telegram bot | 1 | 推送警示與每日摘要、接收訂閱指令 |

---

## 3. Kafka Topic 規劃

### 3.1 原則

- **看板是訊息欄位，不是 topic**：topic 數量與看板數量無關
- **Partition key 用 `post_id`**：用 `board` 會因 Gossiping 量大造成負載不均
- **例外：`crawl.tasks` 的列表任務 key 用 `board`**，讓同一看板固定由同一個爬蟲處理，爬蟲才能在記憶體記住列表推文數（4.2）；文章任務仍用 `post_id`

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
| `__debezium-heartbeat.cdc` | Debezium heartbeat |
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

| 文章年齡 | 重爬頻率 |
|---|---|
| < 1 小時 | 每 2 分鐘 |
| 1～6 小時 | 每 10 分鐘 |
| 6～24 小時 | 每小時 |
| > 24 小時 | 停止 |

**重爬門檻**：文章滿 1 小時後，推文數低於該看板的 `boards.recrawl_min_push` 就停止重爬。依上表每篇 24 小時內約重爬 78 次，Gossiping 一天數千篇會超出請求預算，門檻用來只追蹤有在發酵的文章（Gossiping 預設 10，其餘 0）。

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

#### 設計

- 常駐程式，使用 APScheduler（3.x），**每個看板一個計時器**
- 每 30 秒向 `GET /boards` 同步設定，有變化才新增、移除或 `reschedule` 計時器
- API 失敗時維持現有計時器
- `reschedule` 從重設當下重新起算；要立刻爬就用手動觸發

#### 計時器

| 計時器 | 頻率 | 動作 |
|---|---|---|
| `board:<name>` | 看板的 `interval_sec` | 派發列表頁任務 |
| `sync_boards` | 30 秒 | 同步設定 |
| `dispatch_due_posts` | 30 秒 | 派發到期的文章重爬任務 |

#### 範例

```python
scheduler = AsyncIOScheduler()

def sync_boards():
    try:
        boards = requests.get("http://api/boards", timeout=5).json()
    except Exception:
        return

    for b in boards:
        job_id = f"board:{b['board']}"
        job = scheduler.get_job(job_id)
        if not b["enabled"]:
            if job:
                job.remove()
        elif job is None:
            scheduler.add_job(send_list_task, "interval", seconds=b["interval_sec"],
                              jitter=5, id=job_id, args=[b["board"]])
        elif job.trigger.interval.total_seconds() != b["interval_sec"]:
            job.reschedule("interval", seconds=b["interval_sec"], jitter=5)

scheduler.add_job(sync_boards, "interval", seconds=30, next_run_time=datetime.now())
scheduler.add_job(dispatch_due_posts, "interval", seconds=30)
scheduler.start()
```

#### 限制

- 只能跑 1 個 instance（高可用可用 PG advisory lock）
- 不放進 FastAPI 的 process，獨立部署

### 4.5 文章重爬排程

#### 查詢到期文章

```sql
SELECT p.post_id, p.url
FROM posts p
JOIN boards b USING (board)
LEFT JOIN crawl_state cs USING (post_id)
WHERE p.created_at > now() - interval '24 hours'
  AND NOT p.is_deleted
  AND (p.created_at > now() - interval '1 hour'          -- 1 小時內一律重爬
       OR p.push_count >= b.recrawl_min_push)            -- 之後只追蹤達門檻的
  AND (cs.next_crawl_at IS NULL OR cs.next_crawl_at <= now());
```

派發後依文章年齡算出新的 `next_crawl_at`，寫回 `crawl_state`。

#### 為什麼獨立成 `crawl_state` 表

`next_crawl_at` 放在 `posts` 的話，每次重爬都更新會產生 CDC 事件；不更新則排程不會推進。獨立成表並排除在 Debezium 監聽之外即可解決。

### 4.6 爬蟲

- 屬於同一個 consumer group，消費 `crawl.tasks`，結果寫入 `raw.posts` 與 `raw.html`（皆以 `post_id` 為 key）
- 不碰 PG、不讀設定
- 一次處理一個任務：一個列表任務可能牽動約 20 次請求，整批重試代價高
- **速率限制**：每次請求間隔 2 秒 + 0～2 秒隨機，平均約 3 秒一次；3 個爬蟲合計約 1 次/秒
- **HTTP 回應**：
  - 200、404 正常處理；文章頁 404 視為被刪除，送出 `is_deleted=true` 的快照（推噓數為 0、沒有推文）
  - 429、5xx、逾時、連線錯誤 → 整批重試，不 commit
  - 其他狀態（403、3xx）與解析失敗 → 記錄 ERROR 後略過，不重試，避免卡住 partition
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
- **刪除快照**：只把既有文章的 `is_deleted` 設為 true，保留刪除前的內容；從未見過的文章略過，已標記的不重複寫
- **錯誤處理**：DB 連線錯誤 → 整批重試；其他 DB 錯誤（例如約束違反）直接中止服務，避免資料靜默遺失；格式不合法的訊息由 consumer 送 `dlq`

### 5.2 帶條件的 upsert

```sql
INSERT INTO posts (post_id, board, author, title, content, url,
                   push_count, boo_count, created_at, crawled_at)
VALUES (...)
ON CONFLICT (post_id) DO UPDATE SET
  push_count = EXCLUDED.push_count,
  boo_count  = EXCLUDED.boo_count,
  title      = EXCLUDED.title,
  content    = EXCLUDED.content,
  crawled_at = EXCLUDED.crawled_at
WHERE posts.crawled_at < EXCLUDED.crawled_at                  -- 舊快照不覆蓋新的
  AND (posts.push_count IS DISTINCT FROM EXCLUDED.push_count
    OR posts.boo_count  IS DISTINCT FROM EXCLUDED.boo_count
    OR posts.title      IS DISTINCT FROM EXCLUDED.title       -- 作者可能改標題
    OR posts.content    IS DISTINCT FROM EXCLUDED.content);   -- 沒變化就不寫

INSERT INTO comments (post_id, floor, type, user_id, content, commented_at)
VALUES (...)
ON CONFLICT (post_id, floor) DO NOTHING;
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
  recrawl_min_push INT NOT NULL DEFAULT 0 CHECK (recrawl_min_push >= 0),  -- 4.2 重爬門檻
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

每張表只有一個寫入者。爬蟲不能同時寫 PG 和 Kafka（雙寫）。寫入者與是否被監聽也記在各表的 PG table comment。

- `comments.type` 用 CHECK 約束而非 PG 原生 enum，日後加值不必 `ALTER TYPE`
- 約束名稱依固定命名規則產生（例如 `ck_boards_interval_sec_min`），Alembic 才能穩定地修改

---

## 6. CDC 與 ClickHouse

### 6.1 Debezium

- `table.include.list` 只包含 `posts`、`comments`
- Avro 格式，schema 由 Apicurio 管理
- 開啟 `heartbeat.interval.ms`，避免冷門時段 replication slot 停滯、WAL 累積

### 6.2 ClickHouse 表

使用 Kafka table engine + materialized view 直接消費 topic。

| 表 | Engine | 來源 | 用途 |
|---|---|---|---|
| `posts_latest` | `ReplacingMergeTree(version)` | `cdc.public.posts` | 最新狀態（version 用 `ts_ms` 或 LSN） |
| `posts_history` | `MergeTree` | `cdc.public.posts` | 推噓數變化歷程 |
| `comments` | `MergeTree` | `cdc.public.comments` | 每分鐘新增推文數 |
| `labels` | `MergeTree` | `labels` | 標註結果 |
| `predictions` | `MergeTree` | `predictions` | 推論結果（含 `model_version`） |

- 查詢 `posts_latest` 加 `FINAL` 或用 `argMax`
- 刪除事件以 `is_deleted` 處理

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

### 7.5 模型路線

1. Baseline：TF-IDF + Logistic Regression
2. 進階：fine-tune 中文 BERT（Kaggle / Colab 免費 GPU 訓練，CPU 推論）
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
- 訊息帶 `model_version`

### 8.3 熱度偵測

- 輸入：`cdc.public.comments`、`cdc.public.posts`
- 依文章 / 看板做滑動視窗統計（每 1 分鐘、視窗 10 分鐘），之後擴充到實體、主題（見 15.2）
- 與歷史基準比較（z-score / EWMA），超過門檻寫入 `alerts`
- Quix Streams：純 Python、狀態存 RocksDB 並備份到 changelog topic

### 8.4 Shadow 比較

- 新版模型使用新的 consumer group，與舊版並行
- 結果以 `model_version` 區分，在 ClickHouse 比較

---

## 9. 呈現層

### 9.1 Dashboard

Grafana（接 ClickHouse）或 Streamlit：各看板熱度曲線、話題與情緒分布、實體排行。

### 9.2 Telegram bot

- 推送：消費 `alerts`
- 指令：`/subscribe 台積電`、`/boards`、`/hot`
- 使用 long polling，不需要對外開放 HTTP
- 每日摘要：APScheduler cron trigger，每天 08:00 用 LLM 摘要前一天的熱門話題

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
│   │   ├── crawler.py       # [常駐 ×N]（http、rate_limit、list_cache）
│   │   └── parsers/         # PTT 列表頁與文章頁解析
│   ├── ingest/              # [常駐] main、writer
│   ├── ml/
│   │   ├── labeling/
│   │   │   ├── stream.py    # [常駐] 抽樣標註
│   │   │   └── backfill.py  # [一次性] 初期批次標註
│   │   ├── training/        # [一次性] export / train / evaluate
│   │   └── inference/main.py  # [常駐]
│   ├── streaming/heat.py    # [常駐] Quix Streams
│   └── bot/main.py          # [常駐] Telegram bot
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
| 常駐 | api、scheduler、crawler、ingest、labeling/stream、inference、heat、bot | docker-compose service |
| 一次性 | labeling/backfill、training/* | 手動執行或 Colab |

不使用系統 cron，定時行為都在常駐程式內用 APScheduler 處理。

### 10.3 docker-compose

所有自寫服務共用一個 image，只有 `command` 不同：

```yaml
services:
  api:
    image: radar-app
    command: uvicorn radar.api.main:app --host 0.0.0.0
    restart: unless-stopped
  scheduler:
    image: radar-app
    command: python -m radar.collector.scheduler
    restart: unless-stopped          # 只能 1 個
  crawler:
    image: radar-app
    command: python -m radar.collector.crawler
    restart: unless-stopped
    deploy:
      replicas: 3
  ingest:
    image: radar-app
    command: python -m radar.ingest.main
    restart: unless-stopped
  labeling:
    image: radar-app
    command: python -m radar.ml.labeling.stream
    restart: unless-stopped
  inference:
    image: radar-app
    command: python -m radar.ml.inference.main
    restart: unless-stopped
  heat:
    image: radar-app
    command: python -m radar.streaming.heat
    restart: unless-stopped
  bot:
    image: radar-app
    command: python -m radar.bot.main
    restart: unless-stopped
```

### 10.4 上雲

- 不用託管 Kafka（太貴）
- Terraform 開一台 VM（例如 Oracle Cloud 免費 ARM），VM 上跑 docker-compose

---

## 11. 資源估算

### 11.1 記憶體

| 服務 | 占用 |
|---|---|
| Kafka（KRaft，3 節點） | ~1～1.5GB（實測閒置約 0.9GB） |
| Kafka Connect + Debezium | ~1GB |
| Apicurio | ~0.5GB |
| ClickHouse | ~1GB+ |
| PostgreSQL | ~0.3GB |
| Kafka UI | ~0.3GB |
| 自寫 Python 服務 | ~1～1.5GB |
| **合計** | **約 6～7GB** |

### 11.2 吞吐量

每秒個位數到數百筆事件，不是瓶頸。

### 11.3 減輕負擔

- JVM 服務設定 heap 上限
- Kafka UI 需要時再開
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
- [ ] 一次 INSERT 太多推文 → 超過 PG 65535 個參數上限
- [ ] Debezium 沒開 heartbeat → WAL 塞滿硬碟
- [ ] ClickHouse 用一般 MergeTree 存最新狀態 → 重複列

### 12.3 排程

- [ ] 爬蟲自己讀設定 → 重複爬
- [ ] Scheduler 多個 instance 或放進 FastAPI → 重複派發
- [ ] Scheduler 拿不到設定就停止 → API 一掛資料流就斷
- [ ] 看板頻率沒有下限 → IP 被封鎖
- [ ] 每篇文章都依年齡重爬 → Gossiping 的請求量超出預算（用 `recrawl_min_push` 門檻）

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
| 6 | Dashboard | 視覺化 |
| 7 | BERT + shadow 比較 | 模型比較報告 |
| 8 | Terraform 上雲 | 24 小時運作 |

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

### 15.6 推噓比作為弱標註：列為第 3 階段的驗證實驗

- 疑慮：推噓代表「同不同意這篇文」，不等於「這篇文的情緒」（例如痛罵某公司的文章被大量推）
- 驗證方式：拿 LLM 標註的資料，比較各情緒類別的推噓比分布
- 相關性弱 → 不當標籤，改當獨立指標（共鳴度、爭議度）或模型特徵
- 推文層級的 `推` / `噓` 對「該則推文對文章的態度」可能是較好的弱標註，一併驗證
