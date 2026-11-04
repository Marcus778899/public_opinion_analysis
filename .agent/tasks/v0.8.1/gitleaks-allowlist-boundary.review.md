APPROVE c34dde2

# Review gitleaks-allowlist-boundary（PR #241，第 2 輪）

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| PR 變更範圍（`gh pr diff 241`、`git diff develop...HEAD`） | 只有 `.gitleaks.toml`（D-026 那條的 description 與 regex，2 行）、新檔 `tests/unit/test_gitleaks_allowlist.py`；都在負責檔案內 |
| 和 develop 的完整 diff（`git diff develop HEAD`，13 個檔案） | 另外 11 個檔案（`.env.example`、`BOARD.md`、`docs/development-spec.md`、scheduler／recrawl／session／settings 與它們的測試）是分支開出後 develop 才合進來的 #239 等變更，不是這個 PR 改的，三方合併不會被還原；merge-base（21988ad）之後 develop 沒有動到本 PR 的兩個檔案，不會衝突 |
| 禁區（其他 allowlist、`.gitleaksignore`、CI） | 沒動 |
| 上一輪第 1 點：拿掉 `["']?` | 已改。regex 是 `(?i:(?:^\|[^a-z0-9])(?:rev\|revision\|commit\|sha))\s*[:=]+…`，後半段（值的條件）跟舊版一字不差 |
| 不擴大 D-026 範圍（新放行 ⊂ 舊放行） | 成立。新規則是在舊規則上加「關鍵字前面必須是行首或非英數字」，並把舊的 `[a-zA-Z0-9_]*` 固定為空字串；新規則匹配的字串，舊規則一定也匹配 |
| 上一輪第 2 點：測試 | `"revision": "h"`、`"api_key_sha": "h"`、`'secret_token_rev' = 'h'` 已移到不放行清單；新增 `test_new_regex_match_implies_old_regex_match`（舊 regex 寫成常數）。如果之後有人把 `["']?` 加回來，這個測試會失敗 |
| 驗收條件 2（`SHARED_SECRET`、`PREVIOUS_API_KEY`、`REVOKE_TOKEN` 不放行） | 有參數化測試；本機 `uv run pytest tests/unit/test_gitleaks_allowlist.py -q` 的結果是 `26 passed` |
| 驗收條件 1、3（現有變數照樣放行、CI） | `gh pr checks 241`：Check、Integration Test、Security 三個都是 pass（run 40873695019） |
| Python `re` 與 gitleaks（Go RE2）的差異 | 用 Go `regexp` 實際跑了 15 個樣本（合法的 7 個、密鑰 5 個、帶引號的 key 2 個、`revision_token` 1 個），結果跟單元測試的預期完全一致；`(?i)` 搭配否定字元類別時，兩邊都等於 `[^a-zA-Z0-9]` |
| 寫死設定值、安全 | 沒有新增設定值；這次改動只會縮小放行範圍 |

## 問題

無。

## 不阻擋的觀察

- `SECRET_SHA=<hex40>` 這種名稱以 sha／rev 結尾的寫法，照樣會被放行：舊規則本來就放行，也在 D-026 的文字範圍內。回報與 qa 都有記下這點。
- `test_new_regex_match_implies_old_regex_match` 是條件式斷言：新 regex 沒匹配的樣本會直接通過。不過樣本裡有好幾個新規則會放行的字串（`MACBERT_REV`、`x.sha`、`token-rev`），所以這個測試確實有在驗證。
- 本機沒有 gitleaks，驗收條件 1 是靠 CI Security job 確認的。合併前 develop 又多了 #239，如果合併時 CI 重跑，看一下 Security 是不是還是 pass。
