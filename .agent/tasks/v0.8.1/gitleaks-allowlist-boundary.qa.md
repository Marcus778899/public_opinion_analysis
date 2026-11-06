PASS c34dde2

# QA gitleaks-allowlist-boundary（PR #241，HEAD c34dde2）

## 驗收條件

| 條件 | 結果 | 證據 |
|---|---|---|
| 1. 現有合法 revision 變數照樣放行、gitleaks 無新發現 | PASS（間接） | 本機與 sandbox 都沒有 gitleaks，無法跑 `gitleaks git/dir`；改以 `gh pr checks 241` 的 Security job pass（run 40873695019，headSha 與 PR HEAD 相同 c34dde2）確認。另用 Python 驗 `MACBERT_REV`、`MACBERT_REVISION`、`CKIP_PR_COMMIT`、`rev=`、`sha:`、`commit_sha=`、`COMMIT_SHA='..'` 新 regex 都放行 |
| 2. `SHARED_SECRET`／`PREVIOUS_API_KEY`／`REVOKE_TOKEN` + 40 hex 不放行（有單元測試） | PASS | `uv run pytest tests/unit/test_gitleaks_allowlist.py -q` -> `26 passed`；測試含這三個名稱 |
| 3. `make check` 通過、CI Security 綠 | PASS | `pre-commit run --all-files` 全 Passed（trailing whitespace、end of files、yaml、ruff、ruff format、bandit）；`uv run pytest tests/unit -q` -> `1678 passed in 92.31s`；`gh pr checks 241` -> Check pass、Security pass、Integration Test 驗證時仍 pending（非驗收條件） |

## Review 追加兩項

1. `.gitleaks.toml` 已拿掉 `["']?`：diff 確認 regex 為 `(?i:(?:^|[^a-z0-9])(?:rev|revision|commit|sha))\s*[:=]+…`，後半段與舊版相同。PASS
2. 測試：帶引號 key（`"revision": "h"`、`"api_key_sha": "h"`、`'secret_token_rev' = 'h'`）已移到不放行清單；新增 `test_new_regex_match_implies_old_regex_match`（舊 regex 當常數）。PASS

## 自己找的邊界案例

- 隨機模糊測試：30 萬個由 rev/REV/sha/Commit/revision/SECRET/底線/連字號/點/引號/空白/tab/換行組成的名稱，配 `= : := ==` 與值（40 hex、帶單雙引號、41 hex、尾端空白、39 hex、大寫 hex）。新 regex 命中 31436 筆，其中舊 regex 沒命中的 = 0。即「新 ⊂ 舊」，沒有擴大 D-026 範圍。
- 數學上也成立：新規則是舊規則加上「關鍵字前必須是行首或非英數字」的限制，其餘不變。
- 值的條件未變（39 hex、41 hex 不放行，有測試）。
- 已知且屬舊規則範圍：`SECRET_SHA=<hex40>`（底線視為邊界）仍放行，舊規則本來就放行，不算擴大；review 與回報已記載。
- 未改動其他 allowlist、`.gitleaksignore`、CI；PR 相對 merge-base 只有 `.gitleaks.toml`（4 行）與新測試檔。
- 寫死設定值：本單未新增 port／網址／token。
- 單元測試用 Python `re`，gitleaks 用 RE2；用到的語法兩邊一致，且 Security job 實際通過。

## 問題數量：0
