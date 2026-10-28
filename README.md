# 即時輿情雷達

追蹤 PTT 看板的話題，在討論開始發酵的前幾分鐘偵測並用 Telegram 通知，同時提供情緒分析、推噓與爭議度。給想第一時間掌握 PTT 輿情的個人使用。

## 快速開始

1. 設定：在自己的終端機（不是 agent 的 sandbox）跑 `python3 scripts/check_env.py`，依提示在 `.env` 填入缺少的值（Telegram 需要 `TELEGRAM_BOT_TOKEN`，並在 `TELEGRAM_ALLOWED_CHAT_IDS` 填自己的 chat id——沒填 bot 會拒絕啟動，要開放所有人必須另設 `TELEGRAM_ALLOW_ALL=true`（D-010）；情緒推論需要 `INFERENCE_MODEL_VERSION` 與 `models/` 下的模型；Dashboard 需要自訂 `GRAFANA_ADMIN_PASSWORD` 與 `CLICKHOUSE_GRAFANA_PASSWORD`，不可用 `change-me`）
2. 安裝：`make setup`（Python 3.12、[uv](https://docs.astral.sh/uv/)、Docker；`pre-commit install` 啟用 commit 前檢查）
3. 全部啟動（爬蟲、入庫、CDC、watchdog、API、Grafana、熱度警示、Telegram bot、情緒推論；會對真實 PTT 發請求，自動建表、topic 與 CDC connector）：

   ```bash
   docker compose -f infra/docker-compose.yaml --env-file .env --profile app --profile alerting --profile inference up -d --build --wait
   ```

   指令結束後所有容器都應該是 `running`／`healthy`（`radar_init`、`radar_apicurio_db_init` 是一次性工作，`exited (0)` 是正常的）。

   > **選擇性啟動**：上面的 `--profile` 決定開哪些服務，拿掉就不開。Kafka、PostgreSQL、ClickHouse、Debezium、Grafana、Kafka UI 不分 profile 一律啟動。
   >
   > | profile | 服務 | 什麼時候拿掉／加上 |
   > |---|---|---|
   > | `app` | init、api、scheduler、crawler ×3、ingest、cdc-watchdog | 核心，一定要有 |
   > | `alerting` | heat、bot | 不要 Telegram 通知時拿掉 |
   > | `inference` | inference | `.env` 沒設 `INFERENCE_MODEL_VERSION` 時拿掉 |
   > | `shadow` | inference-shadow | 預設不開；匯入 BERT 模型、設好 `INFERENCE_SHADOW_MODEL_VERSION` 後才加（見下方階段 8 第 5 步） |
   > | `labeling` | label-stream | 預設不開；會持續呼叫 LLM API（花額度），要串流標註時才加 |
   >
   > 注意：指令最後**不要**接服務名稱（例如 `… up -d inference`），接了就只會啟動那個服務和它依賴的基礎設施，其他服務（Grafana、watchdog、api、爬蟲、bot…）都不會起來。

4. 建立看板：`make seed`（api 已在上一步的容器裡，不需要另外 `make api`；Gossiping、Stock、Tech_Job，Scheduler 30 秒內開始爬取）；狀態：`curl localhost:8000/status`
5. 在 Telegram 對 bot 傳 `/start`，用主選單按鈕訂閱看板、看現在熱門與看板概況；Dashboard：瀏覽器開 `http://localhost:<GRAFANA_PORT>`，帳號 `admin`、密碼為 `GRAFANA_ADMIN_PASSWORD`，dashboard「radar」不需手動設定（第 3 步已一併啟動 Grafana）
6. 停止（資料保留在 volume）：

   ```bash
   docker compose -f infra/docker-compose.yaml --env-file .env --profile app --profile labeling --profile inference --profile shadow --profile alerting down --remove-orphans
   ```

7. 檢查：`make check`（lint + 單元測試）；整合測試需要 Docker：

   ```bash
   docker compose -f compose.yaml --env-file .env run --rm test
   ```

端到端測試用假 PTT、獨立 volume，不碰開發資料（開發與 e2e 共用容器名稱，不能同時運作，#41）：

1. 開發環境有在跑就先用第 6 步的指令停掉（不刪 volume）
2. 啟動 e2e 環境：

   ```bash
   docker compose -f infra/docker-compose.yaml -f infra/docker-compose.e2e.yaml --env-file .env --profile app up -d --build --wait
   ```

3. 跑測試：`uv run --env-file .env pytest tests/e2e -m e2e`
4. 停止並刪除 e2e 專用的 volume（不碰開發資料）：

   ```bash
   docker compose -f infra/docker-compose.yaml -f infra/docker-compose.e2e.yaml --env-file .env --profile app down -v --remove-orphans
   ```

標註與訓練（階段 3）的指令見[開發規格](docs/development-spec.md)第 6 章與 [docs/labeling-guideline.md](docs/labeling-guideline.md)。

### BERT 與 shadow 比較（階段 8）

新模型先以 shadow 和現行模型並行推論，結果只寫 ClickHouse `predictions_shadow`，Telegram 與 Dashboard 仍只用現行模型。以下指令都在主目錄、自己的終端機執行；`python -m` 指令要帶 `uv run --env-file .env`，不然會缺 ClickHouse 帳密。細節與門檻見開發規格 7.27。

1. 匯出訓練資料：`uv run --env-file .env python -m radar.ml.training.export`，得到 `data/datasets/` 下的 `.jsonl` 與同名 meta 檔
2. fine-tune（Colab，免費版即可；D-019、D-021、D-024）。要跑兩次：第一次 `macbert`、第二次 `ckip`，每次下載 2 個模型包（一般版與 `-int8` 版），共 4 個：
   1. 瀏覽器開 <https://colab.research.google.com>，用 Google 帳號登入；跳出「開啟筆記本」視窗就選「上傳」，選這個 repo 的 `notebooks/bert_finetune.ipynb`（沒跳視窗就用選單「檔案 → 上傳筆記本」）
   2. 開 GPU：選單「執行階段 → 變更執行階段類型」，硬體加速器選 **T4 GPU** → 儲存。沒開的話第 3 部分會停下來說「沒有 GPU」
   3. 第一次跑：程式格維持 `BASE = "macbert"`（第一個灰底程式格裡，不用改）。按選單「執行階段 → 全部執行」，notebook 會從上往下自動跑
   4. 第一格在裝套件，約 1～3 分鐘。如果跳出「需要重新啟動工作階段」的提示，按「重新啟動」，再按一次「執行階段 → 全部執行」（這是正常的，第二次就不會再跳）
   5. 跑到「2. 上傳訓練資料」會出現「選擇檔案」按鈕，同時選第 1 步產出的兩個檔：`data/datasets/` 裡檔名相同的 `.jsonl` 與 `.meta.json`（按住 ⌘ 複選；有好幾組就選時間最新的那組）。上傳完會印出筆數與各類別數量
   6. 「3. fine-tune」是訓練，最久：跑 50 步後會印「預估總時間 X 小時」，目前資料量（約 3,300 筆）預估在 1 小時內。這段時間**不要關分頁、電腦不要睡眠**，免費版閒置太久會斷線，斷線後檔案全部消失要從頭來
   7. 最後一格會印出兩行 `bert-macbert-<時間>.zip  size=…  sha256=…`，把這兩行複製存起來（第 3 步匯入要對照），瀏覽器會自動下載這兩個 zip 到「下載」資料夾（瀏覽器問「允許下載多個檔案」請按允許；沒下載到就從左側資料夾圖示進 `/content/packages/` 右鍵下載）
   8. 第二次跑：把第一格的 `BASE = "macbert"` 改成 `BASE = "ckip"`，再「執行階段 → 全部執行」，到上傳那格要**重新選一次**同樣兩個檔，其餘同 4～7，得到 `bert-ckip-<時間>.zip` 與 `-int8.zip`
   9. 中途出錯：紅字最後一行會說原因（例如沒開 GPU、上傳的檔不對、預估超過 10 小時要把 `MAX_LEN = 512` 改成 `256`），照著改完再「全部執行」；看不懂就把紅字貼給我
3. 匯入（4 個 zip 各做一次）：先跑 `shasum -a 256 ~/Downloads/bert-*.zip`，每個檔的值要和第 2 步存下來的 `sha256=…` 一樣（`import_model` 只檢查包內檔案有沒有損毀，擋不住整包被換掉）；一致再跑 `uv run --env-file .env python -m radar.ml.training.import_model --zip ~/Downloads/<檔名>.zip`，會放到 `models/<檔名去掉 .zip>/`；同版本已存在不會覆寫
4. 評估：`uv run --env-file .env python -m radar.ml.training.evaluate --model models/<模型版本>`，結果在該資料夾的 `evaluation.md`；依開發規格 7.27「自行決定」挑一個進 shadow
5. 啟動 shadow：`.env` 設 `INFERENCE_SHADOW_MODEL_VERSION`（`models/` 下的資料夾名稱；沒設容器會不斷重啟），再執行：

   ```bash
   docker compose -f infra/docker-compose.yaml --env-file .env --profile app --profile shadow up -d --wait inference-shadow
   ```

6. 比較：shadow 運作至少 3 天、兩版重疊 ≥ 500 篇後，`uv run --env-file .env python -m radar.ml.training.compare --a <現行版本> --b <shadow 版本> --since <shadow 開始時間，例 2026-10-26T00:00:00+00:00>`，輸出 `models/<shadow 版本>/comparison.md` 與 `data/review/disagreements-<a>-vs-<b>.csv`
7. 依比較結果決定是否切換預設模型與 `TELEGRAM_SENTIMENT_MIN_SCORE`

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
| BERT 與 shadow 比較 | v0.8.0 | Colab fine-tune 中文 BERT、匯入 ONNX 模型包、shadow 並行推論、ClickHouse 比較兩版（見上方「BERT 與 shadow 比較」） |

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
| `notebooks/` | Colab fine-tune notebook（甲方執行） |
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
| v0.7.0 | 2026-10-21 | 階段 7：Grafana Dashboard（情緒信心下限為下拉選單）；整合測試改用 compose test 服務並平行執行（#78）；bot 允許清單 fail closed（D-010） |
| v0.8.0 | 2026-10-26 | 階段 8：BERT fine-tune notebook、ONNX 模型包匯入、shadow 並行推論、兩版比較；gitleaks 誤判根治（D-018、D-026） |

## 授權

[PolyForm Noncommercial License 1.0.0](LICENSE)：禁止商業用途。
