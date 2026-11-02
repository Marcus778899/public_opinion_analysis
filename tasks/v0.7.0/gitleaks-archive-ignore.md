# 派工單 gitleaks-archive-ignore

- **類型**：chore
- **負責**：backend
- **目標**：把 v0.6.0 封存派工單裡的 gitleaks 誤判加進忽略清單，讓 CI 的 Security 恢復綠燈
- **背景**：develop 自 27610fd（`docs: 封存 v0.6.0 布告欄與派工單`）起 CI Security 失敗（leaks found: 3），#86、#87 也因此紅燈。推測來源是 `tasks/v0.6.0/ci-gitleaks-ignore*` 引用了舊的誤判內容（`unit_key` 的 PTT 文章 ID、fingerprint），須用本機 gitleaks 逐筆確認不是真密鑰。gitleaks 掃整個歷史，改封存檔無效，只能加忽略
- **設計依據**：`.gitleaksignore` 檔頭的誤判說明；`tasks/v0.6.0/ci-gitleaks-ignore.md`
- **相依**：無
- **負責檔案**：
  - `.gitleaksignore`
- **禁區**：不改其他忽略清單與 CI workflow；不放寬 gitleaks 規則；若任一筆是真密鑰，停下回報，不要加忽略
- **驗收測試**：無
- **驗收條件**：
  - [ ] 3 筆發現逐筆列在回報（fingerprint、內容摘要、為何是誤判）
  - [ ] `.gitleaksignore` 新增這些 fingerprint，檔頭說明補一句「封存派工單引用的誤判內容」
  - [ ] gitleaks 8.30.1 `gitleaks git --redact --no-banner .` 在分支上 0 筆
- **驗證指令**：`gitleaks git --redact --no-banner .`（版本同 CI 的 GITLEAKS_VERSION）
- **回報檔**：`reports/gitleaks-archive-ignore.json`

## 執行資訊（task.py 產生）

- Issue：#88
- 分支：`chore/gitleaks-archive-ignore`（從 develop 開出）
- 工作目錄：`.worktrees/gitleaks-archive-ignore`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
