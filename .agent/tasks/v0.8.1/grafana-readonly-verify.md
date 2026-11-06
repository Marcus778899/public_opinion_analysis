# 派工單 grafana-readonly-verify

- **類型**：test
- **負責**：backend
- **目標**：實測 ClickHouse 唯讀帳號 grafana 的實際權限範圍，補整合測試；權限比預期寬就收緊設定（#122）
- **背景**：資安 v0.7.0 第 6 節：`allow_databases` 不一定能限制 `system` 資料庫；`url()`、`remote()` 這類 table function 能不能用也沒實測過。Grafana image 與 plugin 的 CVE 不在這張單的範圍。開發規格目前由 spec-docs-sync 在改，7.25 威脅表要更新的內容寫進回報的 open_questions。
- **設計依據**：#122；docs/security/v0.7.0.md 第 6 節；開發規格 7.25；`infra/clickhouse/users.d/grafana.xml`
- **相依**：無
- **負責檔案**：
  - `tests/integration/dashboard/test_grafana_readonly.py`（新檔）
  - `infra/clickhouse/users.d/grafana.xml`（只限實測發現權限過寬時收緊）
- **禁區**：不改 Grafana provisioning、dashboard、其他 ClickHouse 帳號；不改既有驗收測試 `tests/integration/acceptance/dashboard/`；不改開發規格
- **驗收測試**：無
- **驗收條件**：
  - [ ] 整合測試用 grafana 帳號實測：可以讀 radar 的表；不能寫入、建表、刪表；`system` 資料庫能讀到哪些表要實測並記錄；`url()`、`remote()`、`file()` 這類 table function 要被拒絕
  - [ ] 實測發現權限過寬，就收緊 `grafana.xml`，並確認 dashboard 既有的整合驗收測試仍然通過
  - [ ] 回報附實際的整合測試指令與輸出；做完用 `down -v` 釋放容器
  - [ ] `make check` 通過
- **驗證指令**：`docker compose --env-file .env -f .worktrees/grafana-readonly-verify/compose.yaml run --rm test`（只跑 dashboard 相關的測試）；`make check`
- **回報檔**：`reports/grafana-readonly-verify.json`

## 執行資訊（task.py 產生）

- Issue：#245
- 分支：`test/grafana-readonly-verify`（從 develop 開出）
- 工作目錄：`.worktrees/grafana-readonly-verify`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
