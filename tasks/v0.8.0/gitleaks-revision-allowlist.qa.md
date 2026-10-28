PASS 7206572

# QA gitleaks-revision-allowlist（PR #170，第二輪）

gitleaks 8.30.1（`$TMPDIR/gitleaks/gitleaks`，同 CI）。diff 只動 `.gitleaks.toml`：一條 allowlist，targetRules=generic-api-key，regexTarget=match；tasks/ 排除與 useDefault 保留。

## 驗收條件
1. 分支掃描 0 筆：PASS。worktree 執行 `gitleaks git --redact --no-banner .` -> `269 commits scanned. no leaks found`，exit 0（含 feat/bert-notebook fdc8226；上輪已對照舊設定為 1 筆）。
2. 反向確認：PASS。暫時 repo 比對「僅預設規則」與「PR 設定」：
   - 仍被抓（與預設相同）：auth_token+40hex、TOKENIZER_SHA+非 hex 40 字、TOKENIZER_REV+38hex（連同預設也只在特定值報）、TOKENIZER_REV+48hex（上輪 FAIL，現已抓）、TOKENIZER_REV+40 大寫 hex（現已抓）、TOKENIZER_REV+40hex 後接 abc（現已抓）
   - 放行：TOKENIZER_REV+40 小寫 hex（雙引號）、`revision: '<40 小寫 hex>'`（YAML 單引號）
   - API_KEY+40hex 另用 6 筆隨機值 x API_KEY／auth_token 共 12 筆：預設 12 筆、PR 設定 12 筆，完全一致。
   - 預設規則數量：設定 `useDefault = true`、未改任何規則，PR 設定只新增 allowlist；以預設比對的偵測筆數一致，未少抓。
3. 不引用 key: value：PASS。回報 json 與 PR 說明 grep 無 20 字以上 hex、無 `名稱 = "值"` 形式。
4. PR CI 全綠：PASS。`gh pr checks 170`：Check pass 45s、Integration Test pass 2m35s、Security pass 22s。

## 上輪問題複查
- 超過 40 位 hex 被放行：已修（48 位被抓）。
- 大寫 hex 被放行：已修（名稱用 `(?i:...)`，值限小寫）。
- CI 未確認：已綠。

## 非阻擋觀察（不列 FAIL，已屬 D-026 接受的剩餘風險範圍）
- 名稱比對是子字串且無左邊界：`shared_secret = "<40 小寫 hex>"` 因含 `sha`（shared）被放行（預設規則會抓）。派工單條件寫「名稱含 sha」，行為符合；worker open_questions 已列同類風險（secret_commit），但未特別提到 shared／preview（含 rev）這類誤中。若要收緊，可要求名稱以 rev／sha 等為詞段（前後為 `_` 或邊界）。
- 本輪沒有新增自動測試（chore 單、驗收測試：無）。
