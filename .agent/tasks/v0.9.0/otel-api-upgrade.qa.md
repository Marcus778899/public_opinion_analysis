PASS f37054f

## 驗收條件對照（第 2 輪）

1. uv.lock opentelemetry-api >= 1.45.2、其他套件不變：通過。
   `git diff --stat develop...HEAD`：`.gitleaks.toml | 10 ++++++++++`、`uv.lock | 6 +++---`（13 insertions, 3 deletions）。
   uv.lock diff 只有 opentelemetry-api 1.45.1 -> 1.45.2 的 version、sdist、wheel；pyproject.toml 與程式碼未動。
   `uv run --frozen` 實裝版本印出 `1.45.2`。
2. osv-scanner 0 個漏洞：通過（CI）。`gh pr checks 346`（run 43818750111）：Check pass 3m24s、Integration Test pass 3m46s、Security pass 22s。
   `gh api .../jobs/133136688786 --jq '.steps[]|[.name,.conclusion]|@tsv'`：
   Secrets (gitleaks) success；Dependencies (osv-scanner) success；SAST (semgrep) success。
3. 單元測試：`UV_PROJECT_ENVIRONMENT=$TMPDIR/venv uv run --frozen pytest tests/unit -q -x -n 4` -> `2246 passed in 62.65s`。

## 追加項（.gitleaks.toml）

- 內容與 8d12e3b 相同的 10 行（allowlist 限 `generic-api-key`、路徑 `^docs/security/v[0-9][0-9.]*\.md$`、值形狀 `^0123[0-9a-f]{0,6}456789[0-9a-f]{0,6}$`，三者 AND），僅追加檔尾。
- `gitleaks git --redact --no-banner .` -> 555 commits scanned, no leaks found。
- scan 通道反例（在 $TMPDIR 用 `gitleaks dir -c .gitleaks.toml`）：
  - docs/security/v9.9.md 放同形狀值 -> 放行
  - src/a.md 放同形狀值（路徑不符）-> 被抓
  - docs/security/v9.8.md 放不同形狀的真密鑰樣式值 -> 被抓
  - 結果 `leaks found: 2`，符合預期；規則窄，不是排除整個路徑或關閉規則。

## 其他

- 無寫死設定值（只動 lock 與 gitleaks 設定）。無未列問題。
- 未重跑 pre-commit（CI Check 已通過）。
