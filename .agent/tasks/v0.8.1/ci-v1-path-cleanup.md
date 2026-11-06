# 派工單 ci-v1-path-cleanup

- **類型**：chore
- **負責**：architect
- **目標**：ci.yml integration job 的「只改文件就略過」判斷拿掉 v1 的 `tasks/`、`reports/`；先改驗收測試不再要求這兩個路徑，再改 ci.yml
- **背景**：agent-v1-cleanup（PR #273）已把流程檔搬到 `.agent/`，v1 的根目錄 `tasks/`、`reports/` 不再使用。`.github/workflows/ci.yml` 第 77–78 行（Detect code changes 步驟）的註解與 grep 規則還列著 `tasks/`、`reports/`，註解寫「驗收測試要求保留」：`tests/unit/acceptance/test_infra/test_compose_static.py` 的 `test_ci_integration_first_step_diffs_changed_files`（約第 297–298 行）要求這兩個路徑出現在步驟文字裡。順序：qa 先依本單改寫該測試（只要求 `docs/`、`.agent/`，並要求不再出現 `tasks/`、`reports/`），lock 後 architect 改 ci.yml。
- **設計依據**：agent-v1-cleanup 派工單與仲裁（`.agent/reports/agent-v1-cleanup.ruling.md`）；本輪範圍「agent-v1-cleanup 清掉 v1 殘留」
- **相依**：無
- **負責檔案**：
  - `.github/workflows/ci.yml`
- **禁區**：`.claude/`、`CLAUDE.md`、`.agent/`（回報除外）、`src/`；只改 Detect code changes 步驟的路徑規則與註解，不動其他 CI 步驟、gitleaks、覆蓋率門檻
- **驗收測試**：
  - `tests/unit/acceptance/test_infra/test_compose_static.py`
- **驗收條件**：
  - [ ] 驗收測試改為要求 `docs/`、`.agent/` 在略過規則裡，且 `tasks/`、`reports/` 不再出現；同檔其他測試不變
  - [ ] ci.yml 的略過規則與註解不再有 `tasks/`、`reports/`；`docs/`、`.agent/`、根目錄 `*.md` 的略過行為不變
  - [ ] `uv run pytest tests/unit -q` 全過
  - [ ] PR 上 CI 全綠
- **驗證指令**：`uv run ruff check . && uv run pytest tests/unit -q`；`grep -n "tasks/\|reports/" .github/workflows/ci.yml`（應無結果）
- **回報檔**：`.agent/reports/ci-v1-path-cleanup.json`

## 執行資訊（ae task 產生）

- Issue：#278
- 分支：`chore/ci-v1-path-cleanup`（從 develop 開出）
- 工作目錄：`.worktrees/ci-v1-path-cleanup`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
