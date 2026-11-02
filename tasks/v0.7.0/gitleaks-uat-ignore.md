# 派工單 gitleaks-uat-ignore

- **類型**：chore
- **負責**：backend
- **目標**：把 UAT v0.7.0 報告裡的 gitleaks 誤判加進忽略清單，讓 CI 的 Security 恢復綠燈
- **背景**：develop 自 7b0386c（`docs: UAT v0.7.0 報告；README 補 Grafana、版本表`）起 CI Security 失敗（leaks found: 1），PR #114 也因此紅燈。來源推測是 `docs/uat/v0.7.0.md` 第 19 行測錯誤密碼的指令 `curl -u admin:uat-wrong-password`（故意用的假密碼），規則可能是 curl-auth-user。gitleaks 掃整個歷史，改報告無效，只能加忽略；須用本機 gitleaks 確認只有這一筆、不是真密鑰
- **設計依據**：`.gitleaksignore` 檔頭的誤判說明；`tasks/gitleaks-archive-ignore.md`（同類前例，PR #89）
- **相依**：無
- **負責檔案**：
  - `.gitleaksignore`
- **禁區**：不改其他忽略清單與 CI workflow；不放寬 gitleaks 規則；不改 `docs/uat/`；若發現是真密鑰或不只一筆，停下回報，不要加忽略
- **驗收測試**：無
- **驗收條件**：
  - [ ] 發現逐筆列在回報（fingerprint、內容摘要、為何是誤判）
  - [ ] `.gitleaksignore` 新增 fingerprint，檔頭說明補一句「UAT 報告測錯誤密碼用的假帳密」
  - [ ] gitleaks 8.30.1 `gitleaks git --redact --no-banner .` 在分支上 0 筆
  - [ ] PR 的 CI 全綠（含 Security）
- **驗證指令**：`gitleaks git --redact --no-banner .`（版本同 CI 的 GITLEAKS_VERSION）
- **回報檔**：`reports/gitleaks-uat-ignore.json`

## 執行資訊（task.py 產生）

- Issue：#115
- 分支：`chore/gitleaks-uat-ignore`（從 develop 開出）
- 工作目錄：`.worktrees/gitleaks-uat-ignore`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-21

### reports/gitleaks-uat-ignore.qa.md

FAIL 95ef462

# 驗證 gitleaks-uat-ignore（commit 95ef462，分支 chore/gitleaks-uat-ignore，PR #116）

## 結論：FAIL（1 個問題）

### 問題 1：新增的檔頭說明本身觸發 curl-auth-user，gitleaks 仍有 1 筆、CI Security 失敗
重現：
1. `cd .worktrees/gitleaks-uat-ignore`
2. gitleaks 8.30.1（官方，scratchpad 的 /private/tmp/claude-501/gitleaks/gitleaks，`version` 輸出 8.30.1）執行 `gitleaks git --redact --no-banner .`
3. 輸出：`181 commits scanned.` / `leaks found: 1`
4. 加 `-r <report.json>` 看明細：fingerprint `95ef462c3de5f6cf78d4041b222c40ba3e457b36:.gitleaksignore:curl-auth-user:4`（規則 curl-auth-user，檔案 .gitleaksignore 第 4 行，commit 95ef462）

原因：檔頭新增的註解第 4 行把 `curl -u <帳號>:<假密碼>` 原文寫進去，被同一條規則在 `.gitleaksignore` 本身再抓一次。原本 7b0386c 那筆已被忽略（不再回報），但新 commit 產生新的一筆，等於換一筆出來。
修法方向（供 manager 補單）：檔頭註解不要出現 `curl -u 帳號:密碼` 的完整字樣（例如改寫成「UAT 報告測錯誤密碼用的假帳密」，不含指令原文）；再用同版本 gitleaks 確認 0 筆。注意若再加忽略該新 fingerprint，commit 變了 fingerprint 又會變，不可行。

### PR CI
`gh pr checks 116`：Security fail（6s，run 39550324546）；Check、Integration Test 驗證當下仍 pending。Security 已紅，驗收條件「CI 全綠」未達成。

## 其餘檢查（通過）
- diff（對 develop）只有 `.gitleaksignore`，+2 行：1 行註解、1 筆 fingerprint。
- 新增 fingerprint 只有一筆：`7b0386c72267117fa573f7e2d83913371bc8dfc4:docs/uat/v0.7.0.md:curl-auth-user:19`。
- 原文確認：`git show 7b0386c:docs/uat/v0.7.0.md` 第 19 行是 UAT 表格 S4「未登入／錯誤密碼」，指令用的是字面為 uat-wrong-password 的假密碼，預期結果為拒絕、實測皆 401。是測試用假帳密，非真密鑰。（此處不貼完整指令字串）
- 檔頭說明已補（第 4 行），內容語意正確，但見問題 1。
- CI 的 GITLEAKS_VERSION 為 8.30.1，與本機驗證版本一致。
- 回報 json 稱「no leaks found」，與實測不符（回報只在加註解前或未重掃）。
- 驗收測試為「無」，沒有其他測試要跑；只改忽略清單，無寫死設定值問題。

manager 補充（修正 qa 建議的後半）：pr.py 用 merge commit 合併（`gh pr merge --merge`），95ef462 會原樣留在 develop 歷史，gitleaks 掃歷史仍會抓到它；只改註解不夠。這一輪請在新 commit 做兩件事：
1. `.gitleaksignore` 檔頭註解改成不含任何 `帳號:密碼` 形式的字樣（例如只寫「UAT 報告測錯誤密碼用的假帳密」）。
2. 新增 fingerprint `95ef462c<完整 SHA>:.gitleaksignore:curl-auth-user:4`（用 `git rev-parse 95ef462` 取完整 SHA；fingerprint 本身不含密碼字樣，不會再被抓）。
不可改寫既有 commit（不 amend、不 rebase、不 force push）。用官方 gitleaks 8.30.1 `gitleaks git --redact --no-banner .` 重掃，附「no leaks found」的實際輸出（上一輪回報與實測不符，這次要貼原始輸出）。
