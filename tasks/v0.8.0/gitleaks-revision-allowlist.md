# 派工單 gitleaks-revision-allowlist

- **類型**：chore
- **負責**：backend
- **目標**：gitleaks 不再把「變數名含 rev／revision／commit／sha、值為 40 位小寫 hex」的版本號判成 generic-api-key，恢復所有分支的 CI Security（D-026）
- **背景**：`feat/bert-notebook` 的 commit fdc8226 推上 origin 後，CI（checkout fetch-depth 0、掃 `--all`）在 develop 與所有 PR 都報 1 筆誤判；歷史不能改。調查、建議設定與已驗證的反例見 `reports/bert-shadow-inference.gitleaks.md`「修法選項」A。延續 D-018 的做法（改設定根治）
- **設計依據**：D-026、D-018；`reports/bert-shadow-inference.gitleaks.md`；gitleaks 8.30.1 設定檔 `[[allowlists]]`（targetRules、regexTarget）用法
- **相依**：無
- **負責檔案**：
  - `.gitleaks.toml`
- **禁區**：不改 CI workflow 與 gitleaks 版本；不改 `.gitleaksignore`；不關閉或放寬任何規則本身，新 allowlist 只能限定 `generic-api-key`；保留既有 `tasks/` 路徑排除與預設規則（extend 預設）；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] gitleaks 8.30.1 `gitleaks git --redact --no-banner .` 在分支上 0 筆（會掃到 origin 上含 fdc8226 的 `feat/bert-notebook`；回報附輸出）
  - [ ] 反向確認：在 `$TMPDIR` 暫時 repo 套用同一份設定，`API_KEY`／`auth_token` 一類名稱配 40 位 hex、以及 rev／sha 名稱配非 hex 或非 40 位的值，都仍會被抓到；預設規則數量不變（回報附輸出）
  - [ ] 回報與 PR 說明不原文引用「key: value」形式的疑似密鑰字串
  - [ ] PR 的 CI 全綠
- **驗證指令**：`gitleaks git --redact --no-banner .`（版本同 CI 的 GITLEAKS_VERSION；本機沒有就照 CI 方式下載到 $TMPDIR）
- **回報檔**：`reports/gitleaks-revision-allowlist.json`

## 執行資訊（task.py 產生）

- Issue：#169
- 分支：`chore/gitleaks-revision-allowlist`（從 develop 開出）
- 工作目錄：`.worktrees/gitleaks-revision-allowlist`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-25

### reports/gitleaks-revision-allowlist.qa.md

FAIL 3248580

# QA gitleaks-revision-allowlist（PR #170）

gitleaks：`$TMPDIR/gitleaks/gitleaks` version 8.30.1（同 CI 的 GITLEAKS_VERSION）。diff 只動 `.gitleaks.toml`（+6 行，一條 allowlist，targetRules=generic-api-key），符合禁區。

## 驗收條件

1. 分支掃描 0 筆：PASS。`gitleaks git --redact --no-banner .`（worktree）輸出 `268 commits scanned. no leaks found`，exit=0。`feat/bert-notebook`（含 fdc8226）在掃描範圍內（`git branch -a --contains fdc8226` 有 local 與 origin）。對照舊設定（develop:.gitleaks.toml）同指令 `leaks found: 1`（`GOOGLE_TOKENIZER_REV = "REDACTED"`，generic-api-key），確認是這筆被放行。
2. 反向確認：FAIL。$TMPDIR 暫時 repo，名稱用 `TOKENIZER_REV` 等含 token 關鍵字者，值為隨機 hex，新舊設定比較：

   | 檔案 | 內容 | 舊設定 | 新設定 | 預期 |
   |---|---|---|---|---|
   | apikey.py | API_KEY + 40 hex | 抓 | 抓 | 抓 |
   | auth.py | auth_token + 40 hex | 抓 | 抓 | 抓 |
   | nonhex.py | TOKENIZER_SHA + 非 hex 40 字 | 抓 | 抓 | 抓 |
   | rev38.py | TOKENIZER_REV + 38 hex | 抓 | 抓 | 抓 |
   | rev48.py | TOKENIZER_REV + 48 hex | 抓 | **放行** | 抓（非 40 位） |
   | upper.py | TOKENIZER_REV + 40 位大寫 hex | 抓 | **放行** | 派工單寫「小寫」，應抓 |
   | ok.py | TOKENIZER_REV + 40 小寫 hex | 抓 | 放行 | 放行 |

   預設規則數量：設定仍 `useDefault = true`，未改規則，未另外計數差異。
3. 不原文引用 key: value：PASS。回報 json 與 PR 說明用 grep 掃過，沒有 20 字以上 hex 或 `名稱 = "長字串"` 形式。
4. PR CI 全綠：未確認。我最後查詢時 Security pass、Integration Test pass、`Check` 仍 pending。

## 問題

1. regex 沒有結尾邊界，超過 40 位的 hex 也會放行。
   - regex：`[0-9a-f]{40}["']?`，後面沒有 `(?![0-9a-f])` 或 `\b`，會吃掉前 40 位。
   - 重現：暫時 repo 寫 `TOKENIZER_REV = "<openssl rand -hex 24 的輸出>"`，套用 PR 的 `.gitleaks.toml` 後 `gitleaks git --redact --no-banner .` 回 0 筆；舊設定回 1 筆。
   - 與驗收條件 2 衝突，也與 worker 回報「rev 名稱配 48 位 hex 仍被抓」不符。
   - 建議：regex 結尾加 `(?![0-9a-fA-F])`，或限定結尾為引號、空白、行尾。
2. `(?i)` 使 `[0-9a-f]` 也吃大寫 hex，派工單目標是「40 位小寫 hex」。
   - 重現：`TOKENIZER_REV = "<40 位大寫 hex>"` 被放行。
   - 建議：只對名稱部分做大小寫不分，如 `(?i:rev|revision|commit|sha)`，值保持小寫。
3. PR #170 的 `Check` job 在驗證時仍 pending，CI 全綠無法確認。修完後須重跑。

## 補測重點（下一輪補成測試或腳本驗證）

- 名稱含 rev／sha 配 48 位 hex、40 位大寫 hex 都要被抓
- 38 位、非 hex、API_KEY／auth_token 配 40 hex 維持被抓
- 放行：TOKENIZER_REV／revision 配 40 位小寫 hex
