PASS f7b6011

# QA joserfc-vuln-upgrade（PR #275）

## 1. uv.lock 只動 joserfc（≥1.7.6）
`git diff develop...HEAD --stat`：uv.lock 1 file, 3 insertions, 3 deletions。
diff 只有 joserfc 的 version（1.7.5 → 1.7.7）、sdist、wheel 三處；其他套件、authlib 未變。1.7.7 高於修正版 1.7.6。僅一個 commit（f7b6011），只改 uv.lock。

## 2. 單元測試與 lint（自己跑）
`uv run pytest tests/unit -q` → `1886 passed in 124.14s`
`uv run ruff check .` → `All checks passed!`

## 3. PR #275 CI（`gh pr checks 275 --watch`）
Check pass 1m51s；Integration Test pass 3m40s；Security pass 26s。
Security job 的 osv-scanner 2.6.0 日誌：`Scanned .../uv.lock file and found 93 packages` → `No issues found`，沒有 GHSA-9pg5-8c7x-5hfx。

## 4. 其他
- 無新增套件、無 pyproject.toml、osv-scanner 設定、忽略清單變動（diff 只有 uv.lock）。
- 無寫死設定值問題（僅 lock 檔）。
- 派工單與回報寫 1.7.6，實際是 1.7.7；回報 open_questions 已說明，不影響驗收。
