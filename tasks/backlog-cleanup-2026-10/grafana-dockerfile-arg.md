# 派工單 grafana-dockerfile-arg

- **類型**：fix
- **負責**：backend
- **通道**：fast
- **目標**：建置 Grafana image 時不再印 InvalidDefaultArgInFrom 警告
- **背景**：UAT v0.7.0 F-3（minor，docs/uat/v0.7.0.md、#112）：`infra/grafana/Dockerfile` 的 FROM 用到沒有預設值的 `ARG GRAFANA_VERSION`，每次 `up --build` 都印警告；建置本身成功。版本號由 compose 的 build args 傳入，來源見開發規格 7.25
- **設計依據**：`docs/development-spec.md` 7.25；`docs/uat/v0.7.0.md` F-3
- **相依**：無
- **負責檔案**：
  - `infra/grafana/Dockerfile`
  - `tests/unit/infra/test_grafana_dockerfile.py`
- **禁區**：不改 Grafana 與 plugin 的實際版本、不改 compose 檔與 `.env.example`；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] `docker compose -f infra/docker-compose.yaml --env-file .env build grafana` 輸出沒有 InvalidDefaultArgInFrom，且建出的 Grafana 與 plugin 版本跟修改前相同（附輸出）
  - [ ] 單元測試檢查 Dockerfile 在 FROM 用到的 ARG 都有預設值或沒有警告來源
  - [ ] `make check` 通過；PR 的 CI 全綠
- **驗證指令**：`make check`；上面的 compose build 指令
- **回報檔**：`reports/grafana-dockerfile-arg.json`

## 執行資訊（task.py 產生）

- Issue：#135
- 分支：`fix/grafana-dockerfile-arg`（從 develop 開出）
- 工作目錄：`.worktrees/grafana-dockerfile-arg`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-21

### 負責檔案更新（manager，取代原欄位：補測試套件需要的 __init__.py）

- **負責檔案**：
  - `infra/grafana/Dockerfile`
  - `tests/unit/infra/__init__.py`
  - `tests/unit/infra/test_grafana_dockerfile.py`
