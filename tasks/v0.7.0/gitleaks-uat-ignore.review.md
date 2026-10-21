APPROVE a34985e

# Review gitleaks-uat-ignore（PR #116，head a34985e）

| 檢查項目 | 結果 | 依據 |
|---|---|---|
| 只改負責檔案 | 通過 | `gh pr view 116 --json files`：只有 `.gitleaksignore`（+3／-0，對 develop） |
| 7b0386c 那筆是誤判 | 通過 | `git show 7b0386c:docs/uat/v0.7.0.md` 第 19 行是 UAT S4「未登入／錯誤密碼」，`curl -u admin:` 後面接的就是 `uat-wrong-password` 這個字面值（grep 命中 1），預期結果是拒絕、實測 401；這是故意錯的密碼，不是真的密鑰 |
| 95ef462 那筆是誤判 | 通過 | `git show 95ef462:.gitleaksignore` 第 4 行只是說明文字，引用的是同一組假帳密（grep 命中 1） |
| 沒有放寬規則、忽略範圍沒有過大 | 通過 | 兩筆都是完整的 `<40 碼 SHA>:<檔案>:curl-auth-user:<行號>` fingerprint，只蓋那一個 commit、那一行；沒有新增 `.gitleaks.toml`、allowlist、路徑或規則層級的排除；SHA 與 `git rev-parse` 一致 |
| 檔頭註解不再觸發規則 | 通過 | 現行第 4 行是「UAT 報告測錯誤密碼用的假帳密」，不含指令原文或 `帳號:密碼` 字樣；非 fingerprint 行都沒有帳密形式 |
| 沒有改寫歷史 | 通過 | `git log`：bd1eaa7 → 95ef462 → a34985e，新的 commit 疊在上面；95ef462 的完整 SHA 沒變 |
| gitleaks 0 筆 | 通過 | 我自己在 worktree 用官方 8.30.1 跑 `gitleaks git --redact --no-banner .`：`182 commits scanned.`、`no leaks found`，exit=0 |
| CI | 通過 | `gh pr checks 116`：Check、Integration Test、Security 都是 pass |
| 寫死設定值、測試 | 不適用 | 只改忽略清單；派工單的驗收測試是「無」 |

備註（非缺陷）：
- 合併用 merge commit，95ef462 會留在歷史，靠第二筆 fingerprint 忽略；日後改寫歷史（rebase、squash）會讓兩筆 fingerprint 失效。
- 我想用 develop 版的忽略清單重掃一次，確認只會冒出這兩筆，但 `--gitleaks-ignore-path` 仍會讀到 worktree 的 `.gitleaksignore`，在暫存 clone 重跑又被權限擋住，所以沒有完成。qa 第 1 輪的報告與第 2 輪 diff 的內容是對得上的（第 1 輪只抓到 7b0386c:19，第 2 輪只多了 95ef462:4），而且 fingerprint 是精確比對，不會蓋到其他發現。
