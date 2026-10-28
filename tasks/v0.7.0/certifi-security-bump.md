# 派工單 certifi-security-bump

- **類型**：chore
- **負責**：backend
- **目標**：把間接相依 certifi 升到修好 PYSEC-2026-4320 的版本（2026.10.19 以上），讓 CI 的 Security job（osv-scanner）恢復綠燈
- **背景**：PR #100 的 CI Security 因 `uv.lock` 的 certifi 2026.7.22 有新公布的弱點（PYSEC-2026-4320，CVSS 9.1）失敗；與 PR #100 的改動無關。只升既有套件版本，不新增套件
- **設計依據**：CLAUDE.md 程式碼規範（新增相依才要 D-編號；本單只升版）
- **相依**：無
- **負責檔案**：
  - `uv.lock`
- **禁區**：只升 certifi（`uv lock --upgrade-package certifi`），不升其他套件；不改 `pyproject.toml`、`src/`、`tests/`、CI 設定
- **驗收測試**：無
- **驗收條件**：
  - [ ] `uv.lock` 的 diff 只有 certifi 的版本與 hash
  - [ ] `make check` 通過
  - [ ] PR 的 CI 全綠（含 Security 的 osv-scanner）
- **驗證指令**：`uv lock --upgrade-package certifi`；`git diff --stat develop`；`make check`
- **回報檔**：`reports/certifi-security-bump.json`

## 執行資訊（task.py 產生）

- Issue：#102
- 分支：`chore/certifi-security-bump`（從 develop 開出）
- 工作目錄：`.worktrees/certifi-security-bump`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
