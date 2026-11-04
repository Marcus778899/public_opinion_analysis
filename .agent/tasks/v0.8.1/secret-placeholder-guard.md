# 派工單 secret-placeholder-guard

- **類型**：fix
- **負責**：backend
- **目標**：`.env` 裡的密碼還是範例值 change-me 時，服務不會啟動（#119）
- **背景**：資安 v0.7.0 M-4。`check_env.py` 只認大寫的 `CHANGE_ME`，而 `.env.example` 的四個密碼（`POSTGRES_PASSWORD`、`CLICKHOUSE_PASSWORD`、`CLICKHOUSE_GRAFANA_PASSWORD`、`GRAFANA_ADMIN_PASSWORD`）寫的是 `change-me`，所以檢查擋不到，compose 的 `:?` 也擋不到。`scripts/check_env.py` 是流程檔，不能改，所以只在專案這一端擋。
- **設計依據**：#119；docs/security/v0.7.0.md M-4；開發規格 7.25「不設預設帳密」；CLAUDE.md「設定只放 .env」
- **相依**：無
- **負責檔案**：
  - `.env.example`（只限這四個密碼的範例值改成 `CHANGE_ME`）
  - `tools/check_secrets.py`（新檔）
  - `infra/docker-compose.yaml`（只限 `init` 的 command，在最前面先跑檢查）
  - `tests/unit/tools/test_check_secrets.py`
  - `docs/development-spec.md`（只限 7.25 威脅表 M-4 那一列與 init 順序說明）
- **禁區**：不改 `scripts/`、其他服務的 compose 設定；不讀 `.env` 檔，只讀環境變數；log 與錯誤訊息不印密碼值
- **驗收測試**：
  - `tests/unit/acceptance/secret-placeholder-guard/`
- **驗收條件**：
  - [ ] 這四個變數只要是空值，或不分大小寫等於 change-me／changeme／change_me，檢查就失敗：非 0 結束，印出變數名稱，不印值
  - [ ] 四個都是其他值時通過，結束碼 0
  - [ ] `init` 先跑檢查，檢查失敗就不做後面的建表、建 topic、migration
  - [ ] `.env.example` 的範例值改成 `CHANGE_ME`，`check_env.py` 就會把它們列成必填
  - [ ] 驗收測試與 `make check` 通過；`grep -rn "TODO(secret-placeholder-guard)" src tests tools` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/secret-placeholder-guard tests/unit/tools`；`make check`；`docker compose -f infra/docker-compose.yaml --env-file .env config` 確認 init 的 command
- **回報檔**：`reports/secret-placeholder-guard.json`

## 執行資訊（task.py 產生）

- Issue：#252
- 分支：`fix/secret-placeholder-guard`（從 develop 開出）
- 工作目錄：`.worktrees/secret-placeholder-guard`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
