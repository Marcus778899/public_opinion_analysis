# 即時輿情雷達：開發流程規格

> 狀態：v0.1，對應設計文件 [realtime-sentiment-radar-design.md](realtime-sentiment-radar-design.md)
> 最後更新：2026-10-06

設計文件回答「要做什麼、為什麼」；本文件回答「怎麼做、做到什麼程度算完成」。兩者衝突時，先修設計文件再改本文件。

## 架構圖

![系統架構圖](architecture.drawio.svg)

- 框線分組對應第 6 章的階段；節點內第二行是 `src/radar/` 下的模組
- 顏色：藍＝自寫服務、橘＝Kafka topic、綠＝儲存（PG、ClickHouse、模型檔）、灰＝外部
- 編輯：用 draw.io 直接開啟 `architecture.drawio.svg`（圖檔內嵌原始圖），存檔後即更新

## 目錄

1. [開發環境與慣例](#1-開發環境與慣例)
2. [共用約定](#2-共用約定)
3. [訊息格式](#3-訊息格式)
4. [開發流程](#4-開發流程)
5. [測試策略](#5-測試策略)
6. [階段規格](#6-階段規格)
7. [設計補充（需回寫設計文件）](#7-設計補充需回寫設計文件)
8. [風險清單](#8-風險清單)

---

## 1. 開發環境與慣例

### 1.1 工具

| 項目 | 選擇 | 備註 |
|---|---|---|
| Python | 3.12 | 所有自寫服務共用 |
| 套件管理 | uv | `pyproject.toml` + `uv.lock` |
| Lint / format | ruff | 已在 pre-commit |
| 安全掃描 | bandit | 已在 pre-commit |
| 測試 | pytest、pytest-asyncio、testcontainers | |
| 設定 | pydantic-settings | 全部從環境變數讀，提供 `.env.example` |
| Kafka client | confluent-kafka | |
| PG 存取 | SQLAlchemy 2.0（driver 用 psycopg 3） | 用法分工見 2.4 |
| DB migration | Alembic | 由 ORM model 自動產生，再人工檢查 |
| Log | loggerhelper 2.0.0（`lib/` 內的 wheel） | `LOG_NAME` 設成服務名稱；訊息中帶 `post_id`（如有）；錯誤可選擇送 Slack |

### 1.2 Repo 結構

採用 src layout：所有 Python 程式碼放在 `src/radar/`，以套件 `radar` 安裝（`uv sync` 會以 editable 模式安裝），import 一律寫 `from radar.xxx import ...`，執行用 `python -m radar.collector.scheduler`。

本文件提到的程式碼路徑（如 `common/schemas.py`、`ml/labeling/backfill.py`）都相對於 `src/radar/`。設計文件 10.1 的結構之外，另外加上：

```
├── src/radar/               # Python 程式碼（見設計文件 10.1）
├── pyproject.toml
├── alembic.ini
├── Makefile                 # 常用指令入口
├── .env.example
├── infra/
│   ├── postgres/migrations/ # Alembic（alembic.ini 放在根目錄）
│   └── kafka/topics.yaml    # topic 定義，由 scripts/create_topics.py 套用
├── scripts/
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/ptt/        # 存下來的 PTT HTML
```

### 1.3 Makefile 指令

| 指令 | 動作 |
|---|---|
| `make up` / `make down` | 啟動 / 關閉 docker-compose |
| `make migrate` | `alembic upgrade head` |
| `make topics` | 依 `topics.yaml` 建立或更新 topic（冪等） |
| `make lint` | ruff + bandit |
| `make test` | 單元測試 |
| `make test-int` | 整合測試（需要 Docker） |

### 1.4 分支與提交

- `main`：可部署版本；`develop`：開發整合
- 功能分支：`feat/s<階段>-<簡述>`，例如 `feat/s1-ptt-parser`，PR 合進 `develop`
- 每個階段驗收通過後，`develop` 合進 `main` 並打 tag `stage-<n>`
- 緊急修正從 `main` 開 `fix/*`，合回 `main` 後由 workflow 同步到 `develop`
- Commit 使用 Conventional Commits：`feat(crawler): ...`、`fix(ingest): ...`

---

## 2. 共用約定

### 2.1 識別碼與時間

- `post_id` = `<board>.<PTT 文章檔名>`，例如 `Stock.M.1759730000.A.1B2`
- 所有時間以 UTC 存放與傳遞（ISO 8601）；PTT 頁面時間是 `Asia/Taipei`，在 parser 轉換
- 推文時間沒有年份：取文章年份，推文月份小於文章月份時年份 +1

### 2.2 Kafka

| 項目 | 規則 |
|---|---|
| 序列化 | 自寫 topic 用 JSON（pydantic model 定義在 `common/schemas.py`）；CDC topic 用 Avro + Apicurio |
| 版本 | 每則 JSON 訊息帶 `schema_version`，只做向後相容的變更（加欄位） |
| Key | 依設計文件：`post_id`；`crawl.tasks` 的列表任務例外，用 `board`（見 7.1） |
| Producer | `acks=all`、`enable.idempotence=true`、`compression.type=zstd` |
| Consumer | 關閉 auto commit，處理完（含寫入下游）才 commit，at-least-once |
| 錯誤處理 | 暫時性錯誤（網路、DB 斷線）：指數退避重試，不 commit；資料錯誤（解析、驗證失敗）：寫入 `dlq` 後 commit |
| 優雅關閉 | 收到 SIGTERM 先處理完當前批次、commit、再關閉 |

### 2.3 DLQ 訊息

```json
{
  "source_topic": "raw.posts", "partition": 1, "offset": 12345,
  "consumer": "ingest", "error": "ValidationError: ...",
  "payload_b64": "...", "failed_at": "2026-10-06T08:00:00Z"
}
```

### 2.4 PostgreSQL

- Schema 只透過 migration 變更，不手動改
- 表定義集中在 `common/db/models.py`（SQLAlchemy ORM model），是 schema 的唯一來源；Alembic 從這裡 autogenerate
- ORM model 只描述 PG 表；Kafka 訊息用 `common/schemas.py` 的 pydantic model，兩者不混用

| 場景 | 寫法 | 理由 |
|---|---|---|
| FastAPI 的 `boards` CRUD、bot 的 `subscriptions` | ORM（`Session`） | 單筆讀寫，ORM 最省事 |
| Ingest 批次 upsert | Core：`postgresql.insert().on_conflict_do_update(where=...)` | 一次寫 500 筆，ORM 逐筆 flush 太慢；帶條件 upsert 需要 Core 才寫得出來 |
| Scheduler 查詢到期文章 | Core `select()` | 只讀，回傳 tuple 即可 |
| Advisory lock、publication、`REPLICA IDENTITY` | `text()` 原生 SQL | 屬於 PG 專屬功能，ORM 不支援 |

- Alembic autogenerate 偵測不到 publication、`REPLICA IDENTITY` 等 PG 專屬設定，這類變更在 migration 中用 `op.execute()` 手寫
- 全部使用同步 API；FastAPI 的同步 endpoint 會在 threadpool 執行，目前流量不需要 async
- 每張表只有一個寫入者（設計文件 5.4）；新增表時必須在 migration 註解寫明寫入者、是否被 Debezium 監聽

---

## 3. 訊息格式

以下是 JSON 範例，正式定義以 `common/schemas.py` 的 pydantic model 為準。

### 3.1 `crawl.tasks`

```json
{
  "schema_version": 1, "task_id": "uuid",
  "type": "list",                 // list | post
  "board": "Stock",
  "url": "https://www.ptt.cc/bbs/Stock/index.html",
  "post_id": null,                // type=post 時必填
  "reason": "schedule",           // schedule | manual | recrawl
  "created_at": "..."
}
```

### 3.2 `raw.posts`

```json
{
  "schema_version": 1, "task_id": "uuid",
  "post_id": "Stock.M.1759730000.A.1B2", "board": "Stock",
  "url": "...", "author": "...", "title": "...", "content": "...",
  "created_at": "...", "crawled_at": "...",
  "push_count": 12, "boo_count": 3, "is_deleted": false,
  "comments": [
    {"floor": 1, "type": "push", "user_id": "...", "content": "...", "commented_at": "..."}
  ]
}
```

- `push_count` / `boo_count` 由內頁推文計算，不用列表頁的數字（列表頁有「爆」「X1」等非數值）

### 3.3 `raw.html`

```json
{"schema_version": 1, "post_id": "...", "url": "...", "crawled_at": "...", "html": "..."}
```

### 3.4 `labels`

```json
{
  "schema_version": 1, "post_id": "...",
  "labeler": "gemini-flash", "version": "prompt-v1", "labeled_at": "...",
  "sentiments": [
    {"target": null, "polarity": "negative"},
    {"target": "台積電", "polarity": "positive"}
  ]
}
```

### 3.5 `predictions`

```json
{
  "schema_version": 1, "post_id": "...", "model_version": "tfidf-lr-20261020",
  "predicted_at": "...", "polarity": "negative",
  "scores": {"positive": 0.1, "negative": 0.7, "neutral": 0.2}
}
```

### 3.6 `alerts`

```json
{
  "schema_version": 1, "alert_id": "uuid",
  "unit_type": "post",            // post | board | entity | topic
  "unit_key": "Gossiping.M.1759730000.A.1B2",
  "board": "Gossiping",
  "window_start": "...", "window_end": "...",
  "value": 85, "baseline": 6.2, "zscore": 7.4,
  "sample_post_ids": ["..."], "created_at": "..."
}
```

---

## 4. 開發流程

### 4.1 每個任務的循環

1. **確認設計**：任務若改變資料流、表或 topic，先改設計文件
2. **介面先行**：先寫 pydantic model / ORM model + Alembic migration / topic 設定，並在 PR 中單獨可審
3. **實作 + 單元測試**
4. **整合測試**：在 compose 環境中跑通
5. **驗收**：對照第 6 章該階段的驗收標準
6. **更新文件**：README 中的啟動方式、本文件的任務勾選

### 4.2 完成定義（Definition of Done）

- [ ] `make lint`、`make test` 通過
- [ ] 新增的 consumer 有整合測試，至少涵蓋：正常處理、重複訊息（冪等）、壞訊息進 DLQ
- [ ] 新增的環境變數已加入 `.env.example`
- [ ] 新增服務已加入 docker-compose，且 `restart: unless-stopped`
- [ ] 不會對 PTT 發出真實請求的測試才能進 CI

---

## 5. 測試策略

| 層級 | 範圍 | 工具 | 執行時機 |
|---|---|---|---|
| 單元 | parser、upsert SQL 組裝、熱度計算、年齡分級 | pytest | 每次 commit（CI） |
| 整合 | 單一服務 + 真實 Kafka / PG | testcontainers | PR（CI） |
| 端到端 | 整個 compose，用假 PTT 伺服器 | 本地 `make e2e` | 每階段驗收 |
| 回放 | 把錄下來的 topic 資料重送，驗證熱度偵測 | 腳本 | 第 5 階段起 |

- **PTT fixture**：每種頁面至少存一份 HTML（一般文、刪除文、爆文、含 IP 的推文、跨年推文、被編輯過的文章），parser 測試只讀 fixture
- **假 PTT 伺服器**：一個小型 FastAPI app，回傳 fixture，並能動態增加推文，供端到端測試模擬「推文持續增加」

---

## 6. 階段規格

規模估計：S = 1～3 天、M = 1 週、L = 2 週以上（以業餘時間計）。

### 階段 0：專案骨架（S）

**目標**：任何人 clone 下來 `make up` 就能起來空的基礎設施。

| ID | 任務 |
|---|---|
| S0-01 | `pyproject.toml`、uv、ruff 設定；修正 pre-commit（見 8.2） |
| S0-02 | docker-compose：Kafka（KRaft 單 broker）、PostgreSQL、Kafka UI（profile `debug`） |
| S0-03 | `common/`：settings、logging、Kafka producer/consumer 包裝（含 DLQ、優雅關閉）、PG 連線池 |
| S0-04 | `infra/kafka/topics.yaml` + `scripts/create_topics.py`（冪等） |
| S0-05 | 共用 Dockerfile（一個 image，靠 `command` 區分服務） |
| S0-06 | GitHub Actions：lint + 單元測試 + 整合測試 |

**驗收**
- `make up && make migrate && make topics` 在乾淨機器上成功
- CI 綠燈

### 階段 1：資料收集到 PG（L）

**目標**：透過 API 管理看板，三個看板的資料持續流入 PG。

| ID | 任務 | 依賴 |
|---|---|---|
| S1-01 | Migration：`posts`、`comments`、`boards`、`crawl_state`（設計文件 5.3，加上 7.2 的欄位） | S0 |
| S1-02 | PTT parser：列表頁、內頁、推文、刪除文；fixture 測試 | — |
| S1-03 | FastAPI：`/boards` CRUD、`POST /boards/{board}/crawl`、`GET /status` | S1-01 |
| S1-04 | 爬蟲：消費 `crawl.tasks`，處理 `list` / `post` 任務，寫 `raw.posts`、`raw.html`；速率限制；列表快取（7.1） | S1-02 |
| S1-05 | Ingest：批次 upsert、同批去重（7.3）、壞訊息進 DLQ | S1-01 |
| S1-06 | Scheduler：`sync_boards`、`board:<name>`、`dispatch_due_posts`；PG advisory lock 保證單一 instance | S1-03 |
| S1-07 | 假 PTT 伺服器 + 端到端測試 | S1-04～06 |
| S1-08 | 種子資料：三個看板的初始設定 | S1-03 |

**初始看板設定**

| 看板 | `interval_sec` | `recrawl_min_push`（見 7.2） |
|---|---|---|
| Gossiping | 60 | 10 |
| Stock | 120 | 0 |
| Tech_Job | 600 | 0 |

**驗收**
- 用 API 新增、停用看板，Scheduler 在 30 秒內反映
- 連續運作 24 小時：三個看板都有新文章進 PG，熱門文章的 `push_count` 有隨時間更新
- 同一批 `raw.posts` 重送兩次，PG 的列內容不變（冪等）
- 停掉爬蟲 10 分鐘再啟動，任務接續處理，不需人工介入
- 對 PTT 的平均請求速率 ≤ 1 次/秒（由爬蟲 log 統計）
- `GET /status` 顯示各看板最後爬取時間與 DLQ 數量

### 階段 2：CDC 與 ClickHouse（M）

**目標**：ClickHouse 看得到推噓數變化歷程。

| ID | 任務 |
|---|---|
| S2-01 | **Spike**：驗證 ClickHouse `AvroConfluent` 能讀 Apicurio 序列化的訊息（見 8.1），結論寫回設計文件 |
| S2-02 | PG：`wal_level=logical`、只包含 `posts`、`comments` 的 publication |
| S2-03 | Kafka Connect + Debezium + Apicurio 加入 compose；connector 設定存在 `infra/debezium/`，用腳本註冊 |
| S2-04 | Debezium 設定：`table.include.list`、heartbeat、`ExtractNewRecordState`（保留 `op`、`ts_ms`，刪除改寫為 `__deleted`） |
| S2-05 | ClickHouse：Kafka engine 表 + materialized view → `posts_latest`、`posts_history`、`comments` |
| S2-06 | ClickHouse：`labels`、`predictions`、`alerts` 的 JSON topic 接入（`JSONEachRow`） |

**驗收**
- `posts_latest FINAL` 的筆數與 PG `posts` 一致（允許 1 分鐘延遲）
- 挑一篇熱門文章，`posts_history` 能畫出推文數隨時間的曲線
- 重爬但內容沒變的文章不產生 CDC 事件（比對 topic offset）
- 連續運作 24 小時，PG replication slot 的 WAL 延遲沒有持續增加

### 階段 3：LLM 標註與 baseline（L）

**目標**：第一版情緒模型與評估分數。

| ID | 任務 |
|---|---|
| S3-01 | 標註 prompt 與輸出 JSON schema（3.4 格式，含對象），10～20 篇手動調整到穩定 |
| S3-02 | `ml/labeling/backfill.py`：從 ClickHouse 依看板分層抽樣，Gemini Flash 標註，限速 |
| S3-03 | 第二個標註者交叉標註；不一致清單輸出成 CSV 供人工檢查 |
| S3-04 | 人工測試集：300 篇，人工標註，**不給任何模型訓練** |
| S3-05 | 推噓比弱標註實驗（設計文件 15.6），結論寫成短報告 |
| S3-06 | `ml/training/`：export → train → evaluate；TF-IDF（字元 n-gram，免斷詞）+ Logistic Regression |
| S3-07 | 模型產物：`models/<model_version>/`，含模型檔與 `model_card.json`（訓練資料版本、指標） |
| S3-08 | `ml/labeling/stream.py`：只處理 `op=c` 事件，用 `hash(post_id) % 100 < 5` 抽樣（重跑結果一致） |

**驗收**
- 標註資料 ≥ 3,000 篇，三個看板都有
- 在人工測試集上回報：LLM 標註 vs 人工的一致率、baseline 的 macro-F1
- 推噓比實驗有明確結論（採用 / 改當特徵 / 不採用）

### 階段 4：推論 consumer（S）

**目標**：新文章自動帶情緒分數。

| ID | 任務 |
|---|---|
| S4-01 | `ml/inference/main.py`：消費 `cdc.public.posts`，啟動時載入指定的 `model_version` |
| S4-02 | 觸發條件：`op=c` 一律推論；`op=u` 只在內文 hash 與本地快取不同時推論（大部分更新只是推噓數） |
| S4-03 | 寫入 `predictions` |

**驗收**
- 新文章從進 PG 到 ClickHouse 出現推論結果，p95 < 1 分鐘
- 推噓數更新不會觸發重複推論（比對 `predictions` 筆數與新文章數）

### 階段 5：熱度偵測與 Telegram bot（L，**MVP**）

**目標**：話題暴增時收到 Telegram 通知。

| ID | 任務 |
|---|---|
| S5-01 | `streaming/heat.py`（Quix Streams）：依 `post_id` 與 `board` 統計推文數，視窗 10 分鐘、每 1 分鐘滑動 |
| S5-02 | 時間基準用 `commented_at`（event time），寬限 5 分鐘；超過 1 小時的舊推文只更新基準、不觸發警示（避免 CDC 初始 snapshot 或首次爬到爆文時誤報） |
| S5-03 | 基準：每個 key 用 EWMA 維護平均與變異數，存在 Quix state |
| S5-04 | 觸發條件（可設定）：z-score ≥ 3 **且** 視窗內推文數 ≥ 30；同一 key 30 分鐘內不重複警示；新 key 需累積 1 小時才啟用 |
| S5-05 | 錄製與回放工具：把真實的 `cdc.public.comments` 存成檔案，可重送到測試 topic |
| S5-06 | Migration：`subscriptions(chat_id, unit_type, unit_key)`，寫入者 bot，不被 Debezium 監聽 |
| S5-07 | `bot/main.py`：long polling；消費 `alerts` 依訂閱推送；指令 `/start`、`/boards`、`/subscribe <board>`、`/unsubscribe`、`/hot` |
| S5-08 | （非 MVP 必要）每日 08:00 LLM 摘要 |

**驗收**
- 回放測試：注入一段人工製造的暴增，2 分鐘內收到 Telegram 通知
- 連續運作 3 天：每個看板每天警示數 ≤ 10，人工檢查「值得看」的比例 ≥ 70%
- 重啟 heat 服務後狀態可恢復，不會重新觸發已發過的警示

### 階段 6：Dashboard（S）

| ID | 任務 |
|---|---|
| S6-01 | Grafana + ClickHouse datasource，以 provisioning 檔版本控管 |
| S6-02 | 面板：各看板推文量曲線、情緒分布、近 24 小時警示列表、熱門文章排行 |

**驗收**：`make up` 後打開 Grafana 不需手動設定即可看到所有面板。

### 階段 7：BERT 與 shadow 比較（M）

| ID | 任務 |
|---|---|
| S7-01 | Colab / Kaggle fine-tune 中文 BERT，匯出 CPU 可用的模型（可考慮 ONNX） |
| S7-02 | 新 inference instance 用新 consumer group 與新 `model_version` 並行 |
| S7-03 | ClickHouse 查詢比較兩版：與人工測試集的 macro-F1、兩版不一致的文章、推論延遲 |

**驗收**：產出比較報告，決定是否切換預設模型。

### 階段 8：上雲（M）

| ID | 任務 |
|---|---|
| S8-01 | 確認所有 image 有 arm64 版本（Oracle 免費 ARM） |
| S8-02 | Terraform：VM、網路、磁碟；VM 上跑 docker-compose |
| S8-03 | Secrets 不進 repo（`.env` 由部署流程注入） |
| S8-04 | PG 每日備份到另一個磁碟或物件儲存 |
| S8-05 | 磁碟使用量監控：Kafka log、PG WAL、ClickHouse |

**驗收**：連續運作 7 天不需人工介入，磁碟使用量穩定。

### 後續階段

| 階段 | 內容 | 前置 |
|---|---|---|
| 9 | 實體熱度：CKIP NER + 自訂詞典，`unit_type=entity` | 階段 5 |
| 10 | 主題熱度：離線 BERTopic + 線上指派，`unit_type=topic` | 階段 9、累積 1 個月以上資料 |
| 11 | aspect-based 模型（利用階段 3 已標註的對象） | 階段 7 |

---

## 7. 設計補充（需回寫設計文件）

寫規格時發現設計文件沒說清楚的地方，以下是決定。

### 7.1 爬蟲如何判斷「推文數沒變就不抓內頁」

設計要求爬蟲不碰 PG，但又要知道列表頁上的推文數有沒有變。

- 列表任務的 Kafka key 用 `board`，同一個看板固定由同一個爬蟲處理
- 爬蟲在記憶體保留 `post_id → 列表推文數` 的 LRU 快取
- 列表上的文章不在快取中或推文數改變 → 抓內頁
- 顯示「爆」的文章視為沒變，交給 `dispatch_due_posts` 定期重爬
- Rebalance 或重啟後快取清空，只會多抓幾次內頁，upsert 會擋掉沒變化的寫入，結果仍正確

### 7.2 重爬請求量超出預算

依設計文件 4.2 的年齡分級，每篇文章 24 小時內會被重爬約 78 次。Gossiping 一天若有 3,000 篇，光重爬就約 2.7 次/秒，容易被封鎖。

- `boards` 加欄位 `recrawl_min_push INT NOT NULL DEFAULT 0`
- 文章滿 1 小時後，推文數低於門檻就停止重爬
- Gossiping 先設 10，依實際請求量調整

### 7.3 Ingest 同一批次內有重複的 `post_id`

PostgreSQL 的 `INSERT ... ON CONFLICT DO UPDATE` 不能在同一個語句裡更新同一列兩次，會直接報錯。批次寫入前先在記憶體依 `post_id` 去重，保留 `crawled_at` 最新的一筆；推文依 `(post_id, floor)` 去重。

### 7.4 推文樓層的穩定性

`floor` 是推文在頁面中的順序。作者編輯文章時可能刪改推文，導致樓層位移、新舊推文對不上。MVP 接受此誤差；若實測影響明顯，再改用 `(user_id, commented_at, content)` 的 hash 當推文識別。

---

## 8. 風險清單

### 8.1 技術風險

| 風險 | 影響 | 對策 |
|---|---|---|
| ClickHouse 讀不了 Apicurio 的 Avro 格式 | 階段 2 卡住 | S2-01 先做 spike；Apicurio 提供 Confluent 相容 API，Debezium 改用 Confluent 格式序列化；不行就讓 ClickHouse 改由小型 Python consumer 寫入 |
| PTT 封鎖 IP | 資料中斷 | 請求速率預算（≤ 1 次/秒）、隨機間隔、7.2 的重爬門檻 |
| PTT 版面改版 | parser 失效 | `raw.html` 保留 3 天可重新解析；parser 失敗進 DLQ，`/status` 可看到 DLQ 數量暴增 |
| Gemini 免費額度政策改變 | 標註成本上升 | 標註腳本抽象化 LLM 呼叫，可切換付費 API 的 Batch 模式 |
| 單機記憶體不足（設計估 5.5～6.5GB） | 服務被 OOM kill | JVM heap 上限；階段 2 完成時實測記憶體 |

### 8.2 現有 repo 設定問題

| 檔案 | 問題 | 修正 |
|---|---|---|
| `.pre-commit-config.yml` | pre-commit 預設只讀 `.pre-commit-config.yaml`，目前檔名不會生效 | 改名為 `.yaml` |
| `.pre-commit-config.yml` | bandit 參數 `"lll"` 少了 `-`，會被當成檔案路徑 | 改為 `"-lll"` |
| `.github/workflows/sync_branch.yml` | `git checkout -B origin/develop` 會建立名為 `origin/develop` 的本地分支，之後 `git push origin develop` 找不到本地 `develop` | 改為 `git checkout -B develop origin/develop` |

以上已於 2026-10-06 第一次 commit 前修正。
