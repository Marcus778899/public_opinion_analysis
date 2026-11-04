# 派工單 agent-v1-cleanup

- **類型**：chore
- **負責**：architect
- **目標**：清掉 agent-engineering v1 殘留：CI 改呼叫 ae ci，刪除根目錄 scripts/、templates/、contracts/
- **背景**：專案已升到 agent-engineering v3.0.1（流程指令改成 ae，布告欄與派工單已搬到 .agent/，commit 043372b）。ci.yml 還在跑 `python3 scripts/coverage_gate.py`；sync_branch.yml 可能也是 v1 寫法。根目錄的 scripts/、templates/、contracts/ 是 v1 的流程副本，v3 用 `.claude/skills/agent-engineering/` 裡的版本。D-006：scripts/ 只放流程腳本，專案程式在 tools/。
- **設計依據**：`.claude/skills/agent-engineering/templates/project/ci.yml`、`sync_branch.yml`；`ae ci` 用法見 `.claude/skills/agent-engineering/lib/agent_engineering/ci.py` 開頭；D-015、D-018、D-026
- **相依**：無
- **負責檔案**：
  - `.github/workflows/ci.yml`
  - `.github/workflows/sync_branch.yml`
  - `scripts/`
  - `templates/`
  - `contracts/`
  - `.coverage-exempt`
  - `.gitignore`
  - `docs/development-spec.md`
- **禁區**：`.claude/`、`CLAUDE.md`、`.agent/`、`src/`、`tests/`；不可放寬 gitleaks 規則或覆蓋率門檻（80%）；不可移除專案原有的 CI 步驟
- **驗收測試**：無
- **驗收條件**：
  - [ ] ci.yml 照範本改用 `ae ci`（coverage-gate、security、sync-branch 依範本有的部分），專案原本的步驟全部保留：kafka／postgres／clickhouse 整合測試、gitleaks（含 D-018、D-026 的設定）、pytest-xdist（D-015）、ruff、單元測試
  - [ ] sync_branch.yml 與範本一致或改用 `ae ci sync-branch`
  - [ ] 根目錄 `scripts/`、`templates/`、`contracts/` 刪除前確認沒有專案自己的程式；回報列出刪了哪些檔
  - [ ] `grep -rn "scripts/" .github .coverage-exempt docs/development-spec.md` 不再指向 v1 流程腳本；`.gitignore` 移除 v1 專用的 `tasks/`、`reports/` 規則（.agent/ 的規則保留）
  - [ ] PR 上 CI 全綠，回報附 CI run 連結與覆蓋率步驟的輸出
- **驗證指令**：`uv run ruff check . && uv run pytest tests/unit -q`；`grep -rn "scripts/" .github .coverage-exempt docs/development-spec.md`；PR 的 CI 結果
- **回報檔**：`.agent/reports/agent-v1-cleanup.json`

## 執行資訊（ae task 產生）

- Issue：#272
- 分支：`chore/agent-v1-cleanup`（從 develop 開出）
- 工作目錄：`.worktrees/agent-v1-cleanup`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`

## 追加 2026-11-02

仲裁（.agent/reports/agent-v1-cleanup.ruling.md）判兩個舊驗收測試因本單刪除 v1 檔案而需改，由 qa 依仲裁修改；這兩個檔加進本單範圍：

- **驗收測試**：
  - `tests/unit/acceptance/secret-placeholder-guard/test_secret_placeholder_guard.py`
  - `tests/unit/acceptance/test_infra/test_compose_static.py`
