PASS 32bd009

## 驗收條件

1. `diff templates/github/workflows/sync_branch.yml .github/workflows/sync_branch.yml` -> 無輸出，exit 0（完全一致，無專案客製）。`git diff origin/develop --stat`：只動 `.github/workflows/sync_branch.yml`（7 增 1 減），未碰禁區。
2. `make check`（worktree，自行執行）：`1114 passed in 9.16s`。
3. PR #131 在 32bd009 的 CI（`gh pr checks 131`，自行等到結束）：
   - Check pass 51s
   - Integration Test pass 2m20s
   - Security pass 24s（gitleaks 誤判已由 #134 修好）

## 其他檢查
- 寫死設定值：檔內只有 github-actions bot 的公開 noreply email，來自範本，無 port、網址、token。
- worktree 無未提交變更。
- 驗收測試為「無」；本單是純 workflow 同步，無可補的邊界情況。

問題數量：0
