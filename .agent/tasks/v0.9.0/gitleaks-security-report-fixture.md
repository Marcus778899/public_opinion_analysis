# 派工單 gitleaks-security-report-fixture

- **類型**：chore
- **負責**：architect
- **通道**：scan
- **目標**：v0.9.0 發版 PR #342 的 CI Security（gitleaks）被資安報告裡引用的假雜湊鍵擋下（generic-api-key），確認是誤判後在忽略設定加窄規則
- **背景**：
  - 被擋的位置：commit d3162782，`docs/security/v0.9.0.md` 第 89 行 `password_value = "0123abc456789def"`，是 security 說明 PR #334 放行範圍時舉的例子，跟測試資料是同一個假值；PR #334 的規則只放行 `tests/` 底下
  - CI 的 gitleaks 掃全部歷史（`gitleaks git --redact .`），改報告內容無法讓檢查通過
  - D-018：不再逐筆加忽略（不用 `.gitleaksignore` fingerprint），用設定規則根治
  - 既有前例：PR #323、PR #334；D-018、D-026 是同類窄規則
  - 若判定不是誤判（真的密鑰），停下回報，不改設定
- **設計依據**：CLAUDE.md 決策分級④（掃描誤判可加窄規則、附理由、證明同格式真密鑰仍會被抓）；`.gitleaks.toml` 既有規則
- **相依**：無
- **負責檔案**：
  - `.gitleaks.toml`
- **禁區**：只改 `.gitleaks.toml`；不排除整個路徑、不關規則、不用 `.gitleaksignore` 逐筆忽略（D-018）；不改 `docs/security/`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 規則只放行這一類誤判（路徑、規則、值的格式都要限縮，不比 PR #334 那條寬太多），附理由註解
  - [ ] 對全部歷史跑 gitleaks（同 CI：`gitleaks git --redact --no-banner .`）0 筆
  - [ ] 證明同格式但在其他路徑、或不同值格式的真密鑰仍會被抓到（附指令與輸出）
- **驗證指令**：`gitleaks git --redact --no-banner --config .gitleaks.toml .`；`pre-commit run --all-files`
- **回報檔**：`.agent/reports/gitleaks-security-report-fixture.json`

## 執行資訊（ae task 產生）

- Issue：#343
- 分支：`chore/gitleaks-security-report-fixture`（從 develop 開出）
- 工作目錄：`.worktrees/gitleaks-security-report-fixture`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
