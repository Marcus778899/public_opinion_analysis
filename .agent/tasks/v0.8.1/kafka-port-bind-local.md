# 派工單 kafka-port-bind-local

- **類型**：fix
- **負責**：backend
- **目標**：Kafka 三個對外 port（9092、9094、9096）改綁 127.0.0.1，只給本機的已知服務與工具連（D-039）
- **背景**：UAT v0.8.1 F-8：`infra/docker-compose.yaml` 的 kafka_1～3 ports 寫成 `"9092:9092"` 等，實際綁 0.0.0.0；Kafka 沒有認證，同網段的人可讀寫 topic。其他服務（postgres、api、apicurio、connect、clickhouse、grafana、kafka-ui）都已綁 `127.0.0.1`（#254／D-035 的寫法）。容器之間走 INTERNAL listener（`kafka_N:29092`），不受影響；主機上 `uv run python -m …`、`tools/` 用 `localhost:9092,…` 連，綁 127.0.0.1 後仍可用。`KAFKA_EXTERNAL_HOST` 是 advertised listener，綁本機後只有 localhost 有意義。
  另外順手修開發規格 7.20 步驟 6 的預期（UAT F-9，屬文件同步）：實測 3 輪收到 1～2 則，不一定是文章警示，改寫成「至少 1 則警示（文章或看板）」並保留怎麼看。
- **設計依據**：D-039；D-035（#254 PG 綁本機的做法）；`docs/uat/v0.8.1.md` F-8、F-9；開發規格 7.20
- **相依**：無
- **負責檔案**：
  - `infra/docker-compose.yaml`
  - `docs/development-spec.md`
- **禁區**：不改 `.env.example`（改了甲方要重跑 check-env；`KAFKA_EXTERNAL_HOST` 只在開發規格說明綁本機後的意義）；不改 listener 設定、其他服務的 ports、`compose.yaml`、`compose.ci.yaml`、e2e compose；不重啟開發環境的 Kafka（甲方決定何時部署）
- **驗收測試**：`tests/unit/acceptance/kafka-port-bind-local/`
- **驗收條件**：
  - [ ] `infra/docker-compose.yaml` 的 kafka_1～3 ports 都是 `127.0.0.1:<port>:<port>`；compose 檔裡沒有任何對外 port 綁 0.0.0.0（沒寫 IP 也算）
  - [ ] `docker compose -f infra/docker-compose.yaml --env-file .env.example config` 能解析，三台 Kafka 的 published port 的 host_ip 是 127.0.0.1
  - [ ] 開發規格有寫 Kafka 只綁本機、主機上的工具用 `localhost:9092,9094,9096`（同一件事只寫一次）；7.20 步驟 6 改成「至少 1 則警示」
  - [ ] `uv run pytest tests/unit -q` 全過
- **驗證指令**：`uv run ruff check . && uv run pytest tests/unit -q`；`docker compose -f infra/docker-compose.yaml --env-file .env.example config`
- **回報檔**：`.agent/reports/kafka-port-bind-local.json`

## 執行資訊（ae task 產生）

- Issue：#283
- 分支：`fix/kafka-port-bind-local`（從 develop 開出）
- 工作目錄：`.worktrees/kafka-port-bind-local`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`

## 追加 2026-11-04

仲裁（.agent/reports/kafka-port-bind-local.ruling.md）判 TEST_WRONG：舊單 infra-secret-guard 的 test_guard_kafka_ports_unchanged 與 D-039 矛盾，由 qa 依仲裁改寫；這個檔加進本單範圍：

- **驗收測試**：`tests/unit/acceptance/infra-secret-guard/test_compose_secret_guard.py`

### .agent/reports/kafka-port-bind-local.ruling.md

TEST_WRONG 6d00d5c

驗收測試 lock 檢查：跟 lock（commit 32ef833）時一樣，沒被改過

| 測試 | 契約條文 | 判定與理由 |
|---|---|---|
| `tests/unit/acceptance/infra-secret-guard/test_compose_secret_guard.py::test_guard_kafka_ports_unchanged` | D-039（kafka_1～3 改綁 127.0.0.1）；派工單驗收條件 1（ports 都是 `127.0.0.1:<port>:<port>`） | 錯。測試鎖定舊值 `"9092:9092"`、`"9094:9094"`、`"9096:9096"`，與 D-039 直接矛盾，任何符合本單的實作都會讓它失敗。應改為：參數化的期望值改成 `"127.0.0.1:9092:9092"`、`"127.0.0.1:9094:9094"`、`"127.0.0.1:9096:9096"`（寫法同同檔 `test_guard_api_depends_only_on_init_and_port_unchanged` 的 `127.0.0.1:8000:8000`），測試名稱可維持或改為 `test_guard_kafka_ports_bound_local`。 |

範圍提醒：此測試檔不在本單「驗收測試」（`tests/unit/acceptance/kafka-port-bind-local/`）範圍內，manager 需先把 `tests/unit/acceptance/infra-secret-guard/test_compose_secret_guard.py` 追加進本單範圍，由 qa 依上述改寫後重新 lock。

契約問題：設計／派工單未列出「受影響的既有驗收測試」，漏了這個舊單測試；非決策分級四類，不需 D-編號。
