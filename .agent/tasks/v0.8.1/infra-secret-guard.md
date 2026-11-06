# 派工單 infra-secret-guard

- **類型**：fix
- **負責**：backend
- **目標**：postgres、clickhouse、grafana 在密碼還是範例值時不啟動；PG 的 port 只綁 127.0.0.1（#254，D-035）
- **背景**：PR #253 讓 `init` 先跑 `tools/check_secrets.py`，但這三個基礎服務在預設 profile，不依賴 `init`，只跑 `make up` 時照樣用範例密碼啟動。`infra/docker-compose.yaml` 的 `${POSTGRES_PORT}:5432` 沒綁本機，同網段連得到。Kafka 對外的 port 屬 #68，不在這張單。來源：reports/secret-placeholder-guard.review.md。
- **設計依據**：#254；D-035；docs/security/v0.7.0.md M-4；開發規格 7.25、7.9；`tools/check_secrets.py`
- **相依**：無
- **負責檔案**：
  - `infra/docker-compose.yaml`（只限：新增一次性檢查服務、postgres／clickhouse／grafana 依賴它、postgres 的 port 綁 127.0.0.1）
  - `tools/check_secrets.py`（只限檢查服務會用到的調整，對 `init` 的行為不變）
  - `tests/unit/tools/test_check_secrets.py`
  - `docs/development-spec.md`（只限 7.25 M-4 那一列與 7.9 啟動順序）
- **禁區**：不改 Kafka、app 服務、e2e compose 的設定；不改 `scripts/`；不讀 `.env`；log 不印密碼值；不刪任何 volume
- **驗收測試**：
  - `tests/unit/acceptance/infra-secret-guard/`
- **驗收條件**：
  - [ ] 預設 profile 有一個一次性的檢查服務；postgres、clickhouse、grafana 用 `service_completed_successfully` 依賴它；檢查失敗時這三個服務都不會啟動
  - [ ] 檢查服務不需要先 build radar-app 也能跑，或能說明為什麼一定要 build；不會讓 `make up` 明顯變慢
  - [ ] postgres 的 port 綁 `127.0.0.1`；整合測試、e2e、CI 都不受影響
  - [ ] 開發規格同步；驗收測試與 `make check` 通過；`grep -rn "TODO(infra-secret-guard)" src tests tools` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/infra-secret-guard tests/unit/tools`；`make check`；用 `.env.example` 的副本跑 `docker compose ... config`，確認依賴與 port（不要用真的 `.env` 貼輸出）
- **回報檔**：`reports/infra-secret-guard.json`

## 執行資訊（task.py 產生）

- Issue：#255
- 分支：`fix/infra-secret-guard`（從 develop 開出）
- 工作目錄：`.worktrees/infra-secret-guard`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

### reports/infra-secret-guard.review.md

REQUEST_CHANGES ec68888

# Review infra-secret-guard（PR #256，base develop）

範圍：`git diff develop...ec68888`（72493bb 驗收測試、ec68888 實作），5 個檔案；對照 tasks/infra-secret-guard.md、#254、D-035、開發規格 7.9／7.25、reports/infra-secret-guard.qa.md。

## 檢查結果

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改 infra/docker-compose.yaml、tools/check_secrets.py、tests/unit/tools/test_check_secrets.py、docs/development-spec.md（7.9、7.25 M-4 兩列）；驗收測試由 qa 的 `test(infra-secret-guard)` commit 加入，worker 沒動 |
| 禁區 | Kafka、app 服務、e2e compose、scripts/ 未改；沒刪 volume |
| 條件 1 一次性檢查服務 | `secret-check` 無 profiles、`restart: "no"`；postgres、clickhouse、grafana 都 `service_completed_successfully`；grafana 保留 clickhouse healthy。apicurio-db-init → postgres、connect／init 經 postgres 間接被擋 |
| 條件 2 不需 build | 純 `python:3.12-slim` 掛載唯讀腳本；腳本只用標準函式庫，`ImportError` 時退回 stderr log；`make up` 的 `up -d --wait` 對一次性服務已有先例（apicurio-db-init、init），不會卡住 |
| 條件 3 PG 綁 127.0.0.1 | `127.0.0.1:${POSTGRES_PORT}:5432`；compose.yaml（整合測試）、compose.ci.yaml、ci.yml 都不用 infra compose；e2e 只覆寫 postgres volume |
| `init` 行為不變 | check_secrets 的判定邏輯與輸出沒變，只多 import 備援；守門測試確認 init 仍先跑檢查 |
| log 不印密碼 | 備援路徑也只印變數名稱；單元測試涵蓋好／壞兩種 env |
| 測試是否測到條件 | 驗收測試靜態檢查依賴條件、profile、restart、port 與既有服務不變；「失敗時不啟動」靠 compose 語意，qa 另用副本實跑 secret-check（結束碼 1／0）佐證，足夠 |
| 文件同步 | 7.9、7.25 與實作一致 |

## 要改的問題

1. infra/docker-compose.yaml:109 — `secret-check` 用 `env_file: ../.env`，把整份 `.env`（含 `GROQ_API_KEY`、`TELEGRAM_BOT_TOKEN` 等與檢查無關的 token）注入一個第三方 image 的容器，`docker inspect radar_secret_check` 也看得到；這個服務只需要四個密碼。另外 env_file 是相對 compose 檔的路徑，從 worktree 下 `-f .worktrees/<id>/infra/docker-compose.yaml` 會找不到檔（qa 證據已記，只能複製到 scratchpad 實跑）— 改成照 apicurio-db-init 的寫法，用 `environment:` 只傳 `POSTGRES_PASSWORD`、`CLICKHOUSE_PASSWORD`、`CLICKHOUSE_GRAFANA_PASSWORD`、`GRAFANA_ADMIN_PASSWORD`（`${KEY:-}`，空值交給腳本判定、印出變數名稱），並加 `network_mode: none`（腳本不需網路）。驗收測試不檢查 env_file，改了不會壞；7.25 M-4 那列不用改。

## qa 兩項觀察的判定（都不用改）

| 觀察 | 判定與理由 |
|---|---|
| `python:3.12-slim` 寫死 | 保留。專案用 `${X_VERSION}` 的是甲方可調的第三方服務版本；這個 tag 是專案自己的 Python 執行環境，跟根目錄 `Dockerfile` 的 `FROM python:3.12-slim`、pyproject 的 `requires-python = ">=3.12"` 同一件事，兩處一致即可。改成變數要動 `.env.example`（不在負責檔案），還會讓 secret-check 與 radar-app 的 Python 版本可以分岔。之後升 Python 時兩處一起改 |
| `container_name: radar_secret_check` 固定 | 保留。這份 compose 每個服務都固定 `radar_*` 名稱，開發與 e2e 互斥的判斷（#41）也依賴這個慣例；`up` 會重用同名的已結束容器，`run` 另取名，不會衝突 |

問題數量：1
