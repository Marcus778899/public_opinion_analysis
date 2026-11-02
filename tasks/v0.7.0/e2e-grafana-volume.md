# 派工單 e2e-grafana-volume

- **類型**：fix
- **負責**：backend
- **目標**：e2e 環境的 Grafana 改用 e2e 專用的資料 volume，README e2e 第 4 步的 down -v 不再刪到開發環境的 radar_grafana_data
- **背景**：UAT v0.7.0 F-1（major，docs/uat/v0.7.0.md）：down -v 輸出有 `Volume radar_grafana_data Removed`，其他 e2e volume 都有 radar_e2e_ 前綴，違反 README「不碰開發資料」。issue #101 同一件事，改在本單修
- **設計依據**：`docs/development-spec.md` 第 5 章 e2e（資料與 log 全改掛 e2e 專用 volume，#29、#41）、7.25；`docs/uat/v0.7.0.md` F-1
- **相依**：無
- **負責檔案**：
  - `infra/docker-compose.e2e.yaml`
  - `docs/development-spec.md`
- **禁區**：不改 `infra/docker-compose.yaml`（開發環境）、`compose.yaml`、`src/`；不改 Makefile 的 e2e 目標行為以外的東西；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：
  - `tests/unit/e2e_support/test_e2e_grafana_volume.py`
- **驗收條件**：
  - [ ] 驗收測試全過，`make check` 通過；既有 `tests/unit/e2e_support/` 測試仍全過
  - [ ] `docker compose -f infra/docker-compose.yaml -f infra/docker-compose.e2e.yaml --env-file .env --profile app config` 的 grafana 不再掛 grafana_data，改掛 e2e 專用 volume（附相關輸出）
  - [ ] 開發規格第 5 章 e2e 的 volume 清單補上 grafana
  - [ ] PR 的 CI 全綠
- **驗證指令**：`make check`；`docker compose -f infra/docker-compose.yaml -f infra/docker-compose.e2e.yaml --env-file .env --profile app config`
- **回報檔**：`reports/e2e-grafana-volume.json`

## 執行資訊（task.py 產生）

- Issue：#113
- 分支：`fix/e2e-grafana-volume`（從 develop 開出）
- 工作目錄：`.worktrees/e2e-grafana-volume`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
