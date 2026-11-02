# 派工單 deps-authlib-upgrade

- **類型**：chore
- **負責**：backend
- **目標**：把 `uv.lock` 裡的 `authlib` 從 1.8.0 升到已修補的版本（≥ 1.9.1），讓 CI 的 Security（osv-scanner）恢復綠燈
- **背景**：2026-10-28 PR #183 的 CI Security 失敗：osv-scanner 報 `authlib` 1.8.0 有 7 個漏洞（GHSA-6v38-4h7w-rj9h critical 9.1；GHSA-7vr2-2fgp-9w7p、GHSA-8m4g-j4wp-wgcg high；另 4 個 medium），修補版 1.9.0／1.9.1。`authlib` 是 `confluent-kafka[avro]` 的間接相依，不是新套件；不擋所有 PR 與 v0.8.0 發版。只升這一個套件，不順手升其他套件
- **設計依據**：`docs/development-spec.md`（相依套件管理）；CLAUDE.md「新增相依套件屬於決策分級②」（本單只升既有間接相依，不新增）
- **相依**：無
- **負責檔案**：
  - `uv.lock`
  - `pyproject.toml`（只在必須加下限約束才能升到修補版時才改，回報說明理由）
- **禁區**：不新增套件；不升級 `authlib` 以外的套件（`uv lock --upgrade-package authlib`，若連帶變動其他套件，在回報列出並說明為什麼無法避免）；不改程式碼
- **驗收測試**：無
- **驗收條件**：
  - [ ] `uv.lock` 的 `authlib` ≥ 1.9.1；其他套件版本沒有不必要的變動
  - [ ] 本機跑 osv-scanner（版本同 `.github/workflows` 的 `OSV_SCANNER_VERSION`）或等同方式確認沒有 authlib 漏洞；若 sandbox 無法下載，回報說明並以 PR 的 CI Security 為準
  - [ ] `make check` 通過；Schema registry／avro 相關單元測試通過
- **驗證指令**：`uv sync`；`make check`
- **回報檔**：`reports/deps-authlib-upgrade.json`

## 執行資訊（task.py 產生）

- Issue：#184
- 分支：`chore/deps-authlib-upgrade`（從 develop 開出）
- 工作目錄：`.worktrees/deps-authlib-upgrade`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
