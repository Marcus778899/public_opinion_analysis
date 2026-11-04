PASS 1e1e5f3

# 驗證：gitleaks-archive-ignore（PR #89）

驗證者自行下載官方 gitleaks v8.30.1 darwin_arm64 到 $TMPDIR，`gitleaks version` 輸出 `8.30.1`（與 .github/workflows/ci.yml 的 GITLEAKS_VERSION "8.30.1" 相同）。

## 驗收條件

1. 3 筆發現逐筆列在回報：通過。回報 open_questions 列出 3 筆 fingerprint（27610fd 的 ci-gitleaks-ignore.qa.md:14、.md:6、.review.md:9）。我用 `git show 27610fd...:tasks/v0.6.0/<檔>` 逐筆看第 14／6／9 行，內容皆為 `"unit_key": "Gossiping.M.1759730000.A.1B2"` 或描述它的敘述（PTT 文章 ID 範例，post_id 格式），不是密鑰；rule 為 generic-api-key 誤認 key 名稱 unit_key。
2. `.gitleaksignore` 新增 3 筆並補檔頭說明：通過。`git diff develop...HEAD` 只新增 3 行 fingerprint，檔頭改為「（含資安報告、封存派工單引用的誤判內容）」。
3. 分支上 0 筆：通過。
   - 分支（HEAD 1e1e5f3）：`gitleaks git --redact --no-banner .` -> `130 commits scanned. no leaks found`，exit 0。
   - 對照：把 develop 的 .gitleaksignore 放進分支 clone 後同指令 -> `WRN leaks found: 3`。證明 3 筆確實就是新增的忽略所蓋掉的，且加忽略前後差別只有這 3 筆。

## 範圍
- `git diff --name-only develop...HEAD` 僅 `.gitleaksignore`；工作樹 `git status --short` 乾淨。未動 CI workflow 與其他忽略清單。

## CI（PR #89，head 1e1e5f3e898f）
- Security：pass（27s）
- Check、Integration Test：驗證當下仍 pending（與本單無關，.gitleaksignore 不影響它們）。

## 其他檢查
- 無寫死設定值；本單無程式碼，無單元測試需求（驗收測試：無）。
- 邊界：忽略以 commit+檔+行為鍵，只涵蓋此 3 筆，不放寬規則；新增的真密鑰仍會被抓到。
- 注意：gitleaks 的 --gitleaks-ignore-path 仍會讀來源目錄的 .gitleaksignore，對照測試因此改在 clone 內換檔。

問題數量：0
