# 派工單 dashboard-grafana-infra

- **類型**：feat
- **負責**：backend
- **目標**：開發環境與測試 compose 加入 Grafana（含 ClickHouse plugin 與唯讀帳號），CI 的整合測試一併啟動（開發規格 7.25 派工順序 1）
- **背景**：設計已核可（PR #86、#94，D-014）；test-infra-compose、test-infra-fast-waits 已合併（PR #95、#97），整合測試走 compose test 服務並以 xdist 平行。dashboard 的測試一律在 radar DB 以唯讀帳號查（7.25 測試環境），看板名稱帶 uuid
- **設計依據**：`docs/development-spec.md` 7.25（版本與 plugin、測試環境、派工順序 1、test_grafana_infra 要驗的）、7.26；`docs/research/dashboard-grafana.md`；D-014
- **相依**：test-infra-fast-waits（已合併）
- **負責檔案**：
  - `infra/docker-compose.yaml`
  - `infra/grafana/Dockerfile`
  - `infra/grafana/provisioning/`
  - `infra/clickhouse/users.d/grafana.xml`
  - `compose.yaml`
  - `compose.ci.yaml`
  - `tests/integration/conftest.py`
  - `.github/workflows/ci.yml`
  - `.env.example`
  - `docs/development-spec.md`
  - `docs/realtime-sentiment-radar-design.md`
- **禁區**：不改 `src/`；不寫 dashboard JSON 與 view（順序 2、3）；不掛 docker socket；grafana 在 compose.yaml 只接 internal network、不開 port；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：
  - `tests/unit/acceptance/dashboard/`
  - `tests/integration/acceptance/dashboard/test_grafana_infra.py`
  - `tests/unit/acceptance/test_infra/test_compose_static.py`
- **驗收條件**：
  - [ ] 驗收測試全過，`make check` 通過
  - [ ] `docker compose --env-file .env -f .worktrees/dashboard-grafana-infra/compose.yaml run --rm test` 全過，附 test_grafana_infra.py 的輸出（離線證據，7.25）；交單前 down -v
  - [ ] PR 的 CI 全綠（Integration Test 啟動 grafana、IT_GRAFANA_URL 已設）
  - [ ] 開發規格 1.3、7.25 回寫選定的版本，設計文件 10.3、11.1 同步；新增的環境變數加到 `.env.example`
  - [ ] 開發環境（專案 radar）的容器與資料不受影響
- **驗證指令**：`make check`；`docker compose --env-file .env -f .worktrees/dashboard-grafana-infra/compose.yaml run --rm test`
- **回報檔**：`reports/dashboard-grafana-infra.json`

## 執行資訊（task.py 產生）

- Issue：#99
- 分支：`feat/dashboard-grafana-infra`（從 develop 開出）
- 工作目錄：`.worktrees/dashboard-grafana-infra`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-20

manager 對回報 open_questions 的決定：

- **負責檔案**：
  - `infra/grafana/dashboards/.gitkeep`
- 第 4 點：同意新增 `infra/grafana/dashboards/.gitkeep`（理由：避免 docker 建出 root 擁有的空目錄），已加進負責檔案。
- 第 7 點：`docs/development-spec.md` 整份都在負責檔案內，7.26 做法 1「grafana 由 dashboard-grafana-infra 之後加入」請改成現況（已加入、見 7.25 測試環境），同一件事只寫一次。
- 第 1 點：`.env` 由甲方補，不用你處理。
改完 commit、更新回報。

## 追加 2026-10-20

範圍更正（manager 上一則追加只寫了新增的檔，程式會以最後一則為準，原清單被蓋掉）。負責檔案以下列為準，另補 qa 建的上層套件檔；不需 worker 動作：

- **負責檔案**：
  - `infra/docker-compose.yaml`
  - `infra/grafana/Dockerfile`
  - `infra/grafana/provisioning/`
  - `infra/grafana/dashboards/.gitkeep`
  - `infra/clickhouse/users.d/grafana.xml`
  - `compose.yaml`
  - `compose.ci.yaml`
  - `tests/integration/conftest.py`
  - `tests/integration/acceptance/__init__.py`
  - `tests/integration/acceptance/dashboard/__init__.py`
  - `.github/workflows/ci.yml`
  - `.env.example`
  - `docs/development-spec.md`
  - `docs/realtime-sentiment-radar-design.md`
