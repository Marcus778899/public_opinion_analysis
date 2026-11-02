# 派工單 ci-gitleaks-ignore

- **類型**：chore
- **負責**：backend
- **目標**：把資安報告裡引用的 PTT 文章 ID 加進 gitleaks 誤判清單，讓 CI 的 Security 恢復綠燈
- **背景**：develop 自 06f7081（提交 `docs/security/v0.6.0.md`）起 CI 的 Security 失敗，#74、#75 也因此紅燈。本機 gitleaks 8.30.1 確認唯一發現是 `06f708152ca9324915476f75df04217a91feb4bd:docs/security/v0.6.0.md:generic-api-key:158`，內容是 `"unit_key": "Gossiping.M.1759730000.A.1B2"`，與 `.gitleaksignore` 既有的 5a4d91f 那筆同一種誤判。gitleaks 掃整個歷史，改報告無效，只能加忽略
- **設計依據**：`.gitleaksignore` 檔頭的誤判說明；`docs/security/v0.6.0.md` 第 158 行
- **相依**：無
- **負責檔案**：
  - `.gitleaksignore`
- **禁區**：不改其他忽略清單（`.semgrepignore` 等）與 CI workflow；不放寬 gitleaks 規則
- **驗收測試**：無
- **驗收條件**：
  - [ ] `.gitleaksignore` 新增上述 fingerprint，並在檔頭說明補一句「資安報告引用的 PTT 文章 ID」
  - [ ] gitleaks 8.30.1 `gitleaks git --redact --no-banner .` 在分支上 0 筆
- **驗證指令**：`gitleaks git --redact --no-banner .`（版本同 CI 的 GITLEAKS_VERSION）
- **回報檔**：`reports/ci-gitleaks-ignore.json`

## 執行資訊（task.py 產生）

- Issue：#76
- 分支：`chore/ci-gitleaks-ignore`（從 develop 開出）
- 工作目錄：`.worktrees/ci-gitleaks-ignore`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
