# 即時輿情雷達

追蹤 PTT 看板的話題，在討論開始發酵的前幾分鐘偵測並用 Telegram 通知，同時提供情緒分析、推噓與爭議度。給想第一時間掌握 PTT 輿情的個人使用。

## 快速開始

1. 設定：在自己的終端機（不是 agent 的 sandbox）跑 `python3 scripts/check_env.py`，依提示在 `.env` 填入缺少的值（Telegram 需要 `TELEGRAM_BOT_TOKEN`，並在 `TELEGRAM_ALLOWED_CHAT_IDS` 填自己的 chat id——沒填 bot 會拒絕啟動，要開放所有人必須另設 `TELEGRAM_ALLOW_ALL=true`（D-010）；情緒推論需要 `INFERENCE_MODEL_VERSION` 與 `models/` 下的模型；Dashboard 需要自訂 `GRAFANA_ADMIN_PASSWORD` 與 `CLICKHOUSE_GRAFANA_PASSWORD`，不可用 `change-me`）
2. 安裝：`make setup`（Python 3.12、[uv](https://docs.astral.sh/uv/)、Docker；`pre-commit install` 啟用 commit 前檢查）
3. 啟動整套服務（會對真實 PTT 發請求；自動建表、topic 與 CDC connector）：

   ```bash
   docker compose -f infra/docker-compose.yaml --env-file .env --profile app --profile alerting up -d --build --wait
   ```

   要情緒推論再加這一行：

   ```bash
   docker compose -f infra/docker-compose.yaml --env-file .env --profile app --profile inference up -d --wait inference
   ```

4. 建立看板：`make seed`（api 已在上一步的容器裡，不需要另外 `make api`；Gossiping、Stock、Tech_Job，Scheduler 30 秒內開始爬取）；狀態：`curl localhost:8000/status`
5. 在 Telegram 對 bot 傳 `/start`，用主選單按鈕訂閱看板、看現在熱門與看板概況；Dashboard：瀏覽器開 `http://localhost:<GRAFANA_PORT>`，帳號 `admin`、密碼為 `GRAFANA_ADMIN_PASSWORD`，dashboard「radar」不需手動設定（第 3 步已一併啟動 Grafana）
6. 停止（資料保留在 volume）：

   ```bash
   docker compose -f infra/docker-compose.yaml --env-file .env --profile app --profile labeling --profile inference --profile alerting down --remove-orphans
   ```

7. 檢查：`make check`（lint + 單元測試；整合測試 `make test-int` 需要 Docker）

端到端測試用假 PTT、獨立 volume，不碰開發資料（開發與 e2e 共用容器名稱，不能同時運作，#41）：

1. 開發環境有在跑就先用第 6 步的指令停掉（不刪 volume）
2. 啟動 e2e 環境：

   ```bash
   docker compose -f infra/docker-compose.yaml -f infra/docker-compose.e2e.yaml --env-file .env --profile app up -d --build --wait
   ```

3. 跑測試：`make e2e`
4. 停止並刪除 e2e 專用的 volume（不碰開發資料）：

   ```bash
   docker compose -f infra/docker-compose.yaml -f infra/docker-compose.e2e.yaml --env-file .env --profile app down -v --remove-orphans
   ```

標註與訓練（階段 3）的指令見[開發規格](docs/development-spec.md)第 6 章與 [docs/labeling-guideline.md](docs/labeling-guideline.md)。

## 功能

| 功能 | 版本 | 說明 |
|---|---|---|
| PTT 爬取與入庫 | v0.6.0 | Scheduler 排程、crawler ×3、ingest 寫入 PostgreSQL；管理 API 管看板 |
| CDC → ClickHouse | v0.6.0 | Debezium 把 PG 變更送進 Kafka，再寫入 ClickHouse 供查詢 |
| 情緒標註與模型 | v0.6.0 | LLM 主標註、Claude 交叉比對、人工測試集、訓練與評估（Stock 重新標註待補，見開發規格第 6 章） |
| 情緒推論 | v0.6.0 | 新文章即時推論情緒，結果寫 ClickHouse |
| 熱度偵測與警示 | v0.6.0 | 依推文速度與平常的倍數發出文章、看板警示（3 天驗收待做，見開發規格第 6 章） |
| Telegram bot | v0.6.0 | 按鈕操作訂閱、現在熱門、看板概況、通知設定；警示含推／噓／箭頭、爭議度與情緒；v0.7.0 起沒設允許清單就拒絕啟動（D-010） |
| Dashboard | v0.7.0 | Grafana 6 個面板：各看板推文量、情緒分布與趨勢、爭議度最高的文章、近 24 小時警示、熱門文章排行（D-014） |

## 架構

| 目錄 | 用途 |
|---|---|
| `src/radar/collector/` | Scheduler 與 crawler |
| `src/radar/ingest/` | 爬取結果寫入 PG |
| `src/radar/cdc/` | CDC 監控 |
| `src/radar/streaming/` | 熱度偵測 |
| `src/radar/ml/` | 標註、訓練、推論 |
| `src/radar/bot/` | Telegram bot |
| `src/radar/api/` | 管理 API |
| `src/radar/common/` | 設定、log、Kafka、DB 共用元件 |
| `infra/` | docker-compose、Kafka、PG、ClickHouse、Debezium 設定 |
| `tools/` | 營運腳本：建 topic、ClickHouse migration、註冊 connector、seed（D-006） |
| `scripts/` | agent 團隊流程腳本 |

設計見 [docs/realtime-sentiment-radar-design.md](docs/realtime-sentiment-radar-design.md)，開發規格見 [docs/development-spec.md](docs/development-spec.md)。

## 開發方式

由 agent 團隊開發（規則見 `CLAUDE.md`）。分支：`main` ← `develop` ← `feat/…`、`fix/…`；每個階段合回 `main` 並打 tag（D-003）。
決策紀錄：`docs/decisions.md`；使用者測試：`docs/uat/`；資安審查：`docs/security/`。

## 版本

| 版本 | 日期 | 內容 |
|---|---|---|
| `stage-1`、`stage-2` | 2026-10 | 爬取入庫、CDC → ClickHouse |
| v0.6.0 | 2026-10-20 | 階段 3～6：情緒標註與模型、推論、熱度警示、Telegram 互動 |
| v0.7.0 | （發版中） | 階段 7：Grafana Dashboard；整合測試改用 compose test 服務並平行執行（#78）；bot 允許清單 fail closed（D-010） |

## 授權

[PolyForm Noncommercial License 1.0.0](LICENSE)：禁止商業用途。
