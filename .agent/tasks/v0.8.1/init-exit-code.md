# 派工單 init-exit-code

- **類型**：fix
- **負責**：backend
- **目標**：`radar_init` 初始化成功時結束碼為 0，失敗時能從 log 看出哪一步失敗（#66）
- **背景**：UAT v0.6.0 F-3（docs/uat/v0.6.0.md）：服務、表與 connector 都正常，但 radar_init 顯示 Exited (255)，`apicurio_db_init` 為 0。先查出 255 的來源（哪一步、是否被重啟中斷、是否某工具在「已存在」時回非 0），再修
- **設計依據**：#66；`docs/development-spec.md` 7.9（初始化順序：migration → topic → ClickHouse → connector）。順序不變
- **相依**：無
- **負責檔案**：
  - `infra/docker-compose.yaml`（只限 `init` 服務）
  - `tools/create_topics.py`
  - `tools/migrate_clickhouse.py`
  - `tools/register_connector.py`
  - `tests/unit/tools/`
  - `tests/unit/acceptance/init-exit-code/`
- **禁區**：不改初始化順序與各工具的冪等語意；不改其他服務；不刪 volume 或資料（實測用 `docker compose ... --profile app run --rm init` 對現有環境重跑，各步驟本來就要冪等）
- **驗收測試**：
  - `tests/unit/acceptance/init-exit-code/`
- **驗收條件**：
  - [ ] 回報寫明 255 的原因與證據
  - [ ] 對已初始化的環境重跑 init，結束碼 0（附實測輸出）
  - [ ] 任一步驟失敗時結束碼非 0，log 有一行說明是哪一步、原因（單元測試涵蓋各工具的失敗路徑）
  - [ ] 驗收測試、`make check` 通過；`grep -rn "TODO(init-exit-code)" src tests tools` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/init-exit-code tests/unit/tools`；`make check`；`docker compose -f infra/docker-compose.yaml --env-file .env --profile app run --rm init`
- **回報檔**：`reports/init-exit-code.json`

## 執行資訊（task.py 產生）

- Issue：#212
- 分支：`fix/init-exit-code`（從 develop 開出）
- 工作目錄：`.worktrees/init-exit-code`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

### reports/init-exit-code.qa.md

FAIL dfee1ba

# init-exit-code 驗證（B）

## 實測

1. `docker compose -f infra/docker-compose.yaml --env-file .env --profile app run --rm init`：輸出 alembic 完成、`all 12 topics up to date`、`clickhouse schema up to date (0 applied)`、`connector radar-cdc updated` / `running`，指令無錯誤回傳（tool 未報非 0）。限制：qa 的 hook 不允許在同一行取 `$?`，結束碼 0 是由「指令成功回傳」推得；`--rm` 容器已刪，`ps -a` 看到的 `radar_init Exited (0) 35 minutes ago` 是 worker 先前那次，不是我這次。
2. `uv run pytest tests/unit/acceptance/init-exit-code -q`：`18 passed in 8.55s`。
3. 全單元 `uv run pytest tests/unit -q -n auto`：`1438 passed`。`ruff check` 通過、`ruff format --check` 296 files already formatted。
4. `grep -rn "TODO(init-exit-code)" src tests tools`：無結果。
5. 派工單驗證指令中的 `tests/unit/tools` 不存在（`ERROR: file or directory not found`），該指令照派工單寫法無法執行。PR 只含 `tests/unit/acceptance/init-exit-code/test_init_exit_code_acceptance.py`（342 行），無程式變更。

## 問題

### 1. 255 的原因推論與環境證據矛盾（驗收條件 1 未達成）
worker 說 255 是「Docker daemon／Docker Desktop VM 重啟」，旁證是 kafka_3 近期重啟。但實際 `ps -a`：

```
radar_kafka_1 Up 20 hours (healthy)
radar_kafka_2 Up 20 hours (healthy)
radar_kafka_3 Up 6 minutes (healthy)
radar_postgres Up 20 hours   radar_clickhouse Up 20 hours   radar_connect Up 19 hours
radar_inference_shadow Exited (137) 22 minutes ago
```
Docker daemon／VM 重啟會讓所有 `unless-stopped` 容器的 uptime 一起重置，但其他容器都連續 19–20 小時，只有 kafka_3 與 shadow 異常。所以 kafka_3 重啟與 shadow 的 137（多半是 OOM／被殺）不能證明 Docker 整體重啟，更不能證明 UAT 當時的 255。該結論目前是猜測，未重現、無當時 log、未查 `docker inspect`／Docker Desktop 事件。「F-3 關閉為非缺陷」的建議缺乏證據。

重現：`docker compose -f infra/docker-compose.yaml --env-file .env --profile app ps -a --format "{{.Name}} {{.Status}}"`，看各容器 uptime。

### 2. 回報檔瑕疵
- `files_changed` 列了 `reports/init-exit-code.json`，但該檔不是負責檔案，只是為過 validate_report 湊數，與實際（無任何程式變更）不符。
- `verification.command` 與派工單都含不存在的 `tests/unit/tools`；驗收條件 3 說「單元測試涵蓋各工具失敗路徑」，目前只靠 acceptance 的子行程測試（18 個），沒有在 `tests/unit/tools/` 的單元測試。若 manager 認為驗收測試已足夠，需修正派工單路徑。

## 條件對照
- 回報寫明 255 原因與證據：FAIL（見問題 1）
- 重跑 init 結束碼 0：PASS（成功回傳；限制見上）
- 失敗時非 0 且 log 說明哪一步：PASS（acceptance 18 個通過；僅限靜態／子行程測試，未實際注入失敗到容器）
- 驗收測試與 check、無 TODO：PASS（`make check` 因 sandbox 無法跑，改跑 ruff＋全單元，皆通過）

## 建議（下一輪）
補查 255 證據（Docker Desktop 日誌、對照 UAT 當時時間點的容器事件），或把 F-3 改為「無法重現，暫不處理」並明說推論未證實，而不是定為 Docker 重啟造成。

manager 補充：
- 問題 1：回報改寫成「無法重現、原因未證實」，列出已排除的可能（工具 main() 失敗路徑為 1、restart: "no"、目前重跑為 0）與無法驗證的原因（UAT 當時 log 已不在）；不要寫成已確定是 Docker 重啟
- 問題 2：`tests/unit/tools` 是派工單寫錯的路徑，驗證指令以 `uv run pytest tests/unit/acceptance/init-exit-code` 為準；本單沒改程式，不需另補單元測試（CLAUDE.md 要求的是新增或修改的函式）。`files_changed` 照 validate_report 要求維持即可，在 summary 註明沒有程式改動
