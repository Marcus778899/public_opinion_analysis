# 派工單 ci-token-order

- **類型**：chore
- **負責**：backend
- **目標**：CI integration job 先跑 `git diff` 再 checkout agent-engineering 工具，token 在 PR 程式執行前就離開程序（#277）；Makefile `setup` 註解改成 `ae check-env setup`（#276）
- **背景**：
  - 資安 v0.8.1 L-3（`docs/security/v0.8.1.md`）：PR 的程式或被污染的相依在 checkout 當下可能讀到 `AE_TOKEN`
  - 「Locate agent-engineering」「Checkout agent-engineering」移到「Detect code changes」之後、「Use Docker Hub mirror」之前；`if` 條件不變；coverage gate 的兩步留在原位；只搬步驟、不拆 job
  - `.gitleaks.toml` 的 `^tasks/` 保留（D-018）
- **設計依據**：`docs/development-spec.md` 7.30 F（#276、#277）與派工順序第 7 列、7.26；D-036、D-042
- **相依**：無
- **負責檔案**：
  - `.github/workflows/ci.yml`
  - `Makefile`
- **禁區**：不改文件（與 7.30 不符時回報 manager）；不改 `.gitleaks.toml`、不改其他 job
- **驗收測試**：
  - `tests/unit/acceptance/ci-token-order/`
- **驗收條件**：
  - [ ] 兩個工具 checkout 步驟在 `git diff` 步驟之後、第一個 `docker compose`／`uv`／`make` 步驟之前，`if` 條件不變
  - [ ] 工具 checkout 有 `persist-credentials: false`
  - [ ] Makefile 不再提 `check_env.py`
  - [ ] 7.26 的 `test_ci_integration_first_step_diffs_changed_files` 照樣通過；`make check` 通過、CI 綠燈
- **驗證指令**：`make check`；`uv run pytest tests/unit/acceptance/ci-token-order -v`
- **回報檔**：`.agent/reports/ci-token-order.json`

## 執行資訊（ae task 產生）

- Issue：#300
- 分支：`chore/ci-token-order`（從 develop 開出）
- 工作目錄：`.worktrees/ci-token-order`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
