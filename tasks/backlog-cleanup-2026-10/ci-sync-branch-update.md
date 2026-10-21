# 派工單 ci-sync-branch-update

- **類型**：chore
- **負責**：architect
- **目標**：`.github/workflows/sync_branch.yml` 同步成上游範本新版（`templates/github/workflows/sync_branch.yml`）
- **背景**：甲方 a7070f9 更新範本：release.py finish 會在本機先把 main 併回 develop 並 push，workflow 加了「develop 已包含 main 就算成功」的保底；專案的 workflow 還是舊版，發版時可能因 push 被搶先而失敗
- **設計依據**：`templates/github/workflows/sync_branch.yml`
- **相依**：無
- **負責檔案**：
  - `.github/workflows/sync_branch.yml`
- **禁區**：不改 `templates/`、`scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`；不改其他 workflow
- **驗收測試**：無
- **驗收條件**：
  - [ ] `diff templates/github/workflows/sync_branch.yml .github/workflows/sync_branch.yml` 沒有差異，或差異只有專案原本就客製的部分（回報逐項說明）
  - [ ] `make check` 通過；PR 的 CI 全綠
- **驗證指令**：`diff templates/github/workflows/sync_branch.yml .github/workflows/sync_branch.yml`；`make check`
- **回報檔**：`reports/ci-sync-branch-update.json`

## 執行資訊（task.py 產生）

- Issue：#128
- 分支：`chore/ci-sync-branch-update`（從 develop 開出）
- 工作目錄：`.worktrees/ci-sync-branch-update`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
