# 派工單 gitleaks-archive-allowlist

- **類型**：chore
- **負責**：backend
- **目標**：gitleaks 不再掃 `tasks/` 底下的封存，封存派工單不再讓 CI Security 紅燈（D-018）
- **背景**：v0.6.0、v0.7.0、backlog 清理三次封存都觸發 generic-api-key 誤判（PR #89、#134、#150），每次修正單的報告又成為下一次誤判來源。甲方決定改設定根治（D-018），不再逐筆加 fingerprint。CI 在 `.github/workflows/ci.yml` 以 `gitleaks git --redact --no-banner .` 掃整個歷史
- **設計依據**：D-018；`.gitleaksignore` 檔頭；gitleaks 8.30.1 設定檔的 allowlist（paths）用法
- **相依**：無
- **負責檔案**：
  - `.gitleaks.toml`
  - `.gitleaksignore`
- **禁區**：不改 CI workflow 與 gitleaks 版本；不關閉或放寬任何規則本身，只排除 `tasks/` 路徑；預設規則必須保留（設定檔要 extend 預設規則）；`.gitleaksignore` 只能刪掉因本設定而多餘、且在回報逐筆列出的項目；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] gitleaks 8.30.1 `gitleaks git --redact --no-banner .` 在分支上 0 筆，且暫時移除 `.gitleaksignore` 中 `tasks/` 相關項目後仍為 0 筆（回報附輸出）
  - [ ] 反向確認：在 `$TMPDIR` 建一個暫時 repo，於 `tasks/` 以外放一個假的 generic-api-key 字串，套用同一份設定仍會被抓到；預設規則數量不變（回報附輸出）
  - [ ] 回報與 PR 說明描述誤判時不原文引用「key: value」形式的字串
  - [ ] PR 的 CI 全綠
- **驗證指令**：`gitleaks git --redact --no-banner .`（版本同 CI 的 GITLEAKS_VERSION；本機沒有就照 CI 方式下載到 $TMPDIR）
- **回報檔**：`reports/gitleaks-archive-allowlist.json`

## 執行資訊（task.py 產生）

- Issue：#151
- 分支：`chore/gitleaks-archive-allowlist`（從 develop 開出）
- 工作目錄：`.worktrees/gitleaks-archive-allowlist`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
