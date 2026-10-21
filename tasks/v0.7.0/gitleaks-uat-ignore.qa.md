PASS a34985e

# 驗證 gitleaks-uat-ignore（第 2 輪，commit a34985e，PR #116）

## 結論：PASS（0 個問題）

## 逐項證據
- 95ef462 未被改寫：`git merge-base --is-ancestor 95ef462 HEAD` exit 0；`git rev-parse 95ef462` 為 95ef462c3de5f6cf78d4041b222c40ba3e457b36（與上輪相同）。
- 新 commit 的 diff：`git diff 95ef462 HEAD --stat` 只有 `.gitleaksignore`（2 insertions、1 deletion）；對 develop（bd1eaa7）只有該檔 +3 行（1 行註解、2 筆 fingerprint）。`git status --short` 乾淨。
- 註解內容：新增註解為「UAT 報告測錯誤密碼用的假帳密」，不含 curl 指令、`帳號:密碼` 形式；grep 檢查非 fingerprint 行中無帳密形式字樣（0 筆）。
- 新增兩筆 fingerprint 都對應假帳密：
  - `7b0386c7…:docs/uat/v0.7.0.md:curl-auth-user:19`：該 commit 該檔第 19 行是 UAT S4「未登入／錯誤密碼」，內含字面為 uat-wrong 的假密碼（grep 命中 1），預期結果為拒絕。
  - `95ef462c…:.gitleaksignore:curl-auth-user:4`：該 commit 檔頭註解第 4 行，只是引用上述假帳密的說明文字（grep 命中 1），非真密鑰。
- gitleaks（官方 8.30.1，與 CI GITLEAKS_VERSION 相同）於分支 HEAD，worktree 內執行：

```
$ gitleaks version
8.30.1
$ gitleaks git --redact --no-banner . ; echo "exit=$?"
INF Unknown SCM platform. Use --platform to include links in findings. host=github-personal
INF 182 commits scanned.
INF scanned ~7211946 bytes (7.21 MB) in 1.29s
INF no leaks found
exit=0
```

- PR #116 head 為 a34985ede1516e80adcba7af9896cd786a1d24ee（即本次驗證 commit），`gh pr checks 116 --watch` 最終：

```
Check	pass	46s
Integration Test	pass	2m10s
Security	pass	33s
```

## 其他
- 驗收測試為「無」；只改忽略清單，無寫死設定值。
- 提醒（非缺陷）：合併採 merge commit，95ef462 會留在歷史，靠本次的第二筆 fingerprint 忽略；日後不可改寫歷史，否則 fingerprint 失效。
