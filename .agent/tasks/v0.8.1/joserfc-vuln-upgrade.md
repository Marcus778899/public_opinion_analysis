# 派工單 joserfc-vuln-upgrade

- **類型**：chore
- **負責**：backend
- **目標**：把間接相依 joserfc 從 1.7.5 升到 1.7.6，修 osv-scanner 回報的 GHSA-9pg5-8c7x-5hfx（Medium 6.9），讓 CI Security job 恢復綠燈
- **背景**：2026-11-02 PR #273 的 Security job 失敗（run 41404380986），osv-scanner 掃 uv.lock 發現 joserfc 1.7.5 有漏洞，修正版 1.7.6。joserfc 經 confluent-kafka[avro/json/protobuf/schemaregistry] → authlib 間接引入，不是新套件。現在所有 PR 的 Security job 都會紅。
- **設計依據**：https://osv.dev/GHSA-9pg5-8c7x-5hfx；D-007（相依管理）
- **相依**：無
- **負責檔案**：
  - `uv.lock`
- **禁區**：不新增套件、不升其他套件（只動 joserfc，uv 若必須連帶升 authlib 要在回報說明理由）；不改 osv-scanner 設定或加忽略清單；不改 pyproject.toml
- **驗收測試**：無
- **驗收條件**：
  - [ ] uv.lock 裡 joserfc 是 1.7.6 以上，其他套件版本不變（回報附 `git diff uv.lock` 摘要）
  - [ ] 單元測試全過
  - [ ] PR 上 CI 全綠（含 Security 的 osv-scanner）
- **驗證指令**：`uv lock --upgrade-package joserfc && uv sync && uv run pytest tests/unit -q`；`git diff --stat uv.lock`
- **回報檔**：`.agent/reports/joserfc-vuln-upgrade.json`

## 執行資訊（ae task 產生）

- Issue：#274
- 分支：`chore/joserfc-vuln-upgrade`（從 develop 開出）
- 工作目錄：`.worktrees/joserfc-vuln-upgrade`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
