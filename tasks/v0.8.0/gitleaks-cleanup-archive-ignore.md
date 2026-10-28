# 派工單 gitleaks-cleanup-archive-ignore

- **類型**：chore
- **負責**：backend
- **目標**：把 backlog 清理封存引入的 gitleaks 誤判加進忽略清單，讓 CI 的 Security 恢復綠燈
- **背景**：develop 自 `docs: 封存 backlog 清理（2026-10）` 起 CI Security 的 gitleaks 失敗（leaks found: 2，run 39593065294）。與 tasks/backlog-cleanup-2026-10/gitleaks-v070-archive-ignore.md 同一類：封存檔引用舊誤判內容。gitleaks 掃整個歷史，改封存檔無效，只能加忽略；須逐筆確認不是真密鑰
- **設計依據**：`.gitleaksignore` 檔頭的誤判說明；`tasks/backlog-cleanup-2026-10/gitleaks-v070-archive-ignore.md`
- **相依**：無
- **負責檔案**：
  - `.gitleaksignore`
- **禁區**：不改其他忽略清單與 CI workflow；不放寬 gitleaks 規則；若任一筆是真密鑰，停下回報，不要加忽略
- **驗收測試**：無
- **驗收條件**：
  - [ ] 2 筆發現逐筆列在回報（fingerprint、內容摘要、為何是誤判）
  - [ ] `.gitleaksignore` 新增這些 fingerprint
  - [ ] gitleaks 8.30.1 `gitleaks git --redact --no-banner .` 在分支上 0 筆；PR 的 CI Security 綠
- **驗證指令**：`gitleaks git --redact --no-banner .`（版本同 CI 的 GITLEAKS_VERSION）
- **回報檔**：`reports/gitleaks-cleanup-archive-ignore.json`

## 執行資訊（task.py 產生）

- Issue：#149
- 分支：`chore/gitleaks-cleanup-archive-ignore`（從 develop 開出）
- 工作目錄：`.worktrees/gitleaks-cleanup-archive-ignore`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
