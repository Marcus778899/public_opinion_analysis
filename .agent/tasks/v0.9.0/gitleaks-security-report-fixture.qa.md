PASS 8d12e3b

# QA 證據：gitleaks-security-report-fixture（PR #344，scan 通道）

唯讀驗證；變更只有 `.gitleaks.toml` +10 行（相對 develop 另有 BOARD.md 差異，是 develop 往前走，非本單改動）。

## 1. 規則範圍（驗收條件 1）
新增 allowlist：targetRules=generic-api-key、condition=AND、paths `^docs/security/v[0-9][0-9.]*\.md$`、
regexTarget=secret、值 `^0123[0-9a-f]{0,6}456789[0-9a-f]{0,6}$`（與 PR #334 同形狀）。
路徑、規則、值三項皆限縮；未排除整個路徑、未關規則、未用 .gitleaksignore；有理由註解。

## 2. 全歷史掃描（驗收條件 2）
`gitleaks git --redact --no-banner .`（同 CI）：550 commits scanned, no leaks found, exit 0
`gitleaks git --redact --no-banner --config .gitleaks.toml .`：550 commits scanned, no leaks found

## 3. 反例（驗收條件 3）
在 $TMPDIR 暫存 repo（已刪除）用本 PR 設定掃，10 個檔案：
- 放行（預期）：docs/security/v0.9.0.md（0123d82b456789e6c307）；docs/security/v1.0.md（0123abc456789def）
- 仍被抓 9 筆：
  - docs/design/x.md、docs/security/notes.md、src/x.py（同值、其他路徑/非版本檔名）
  - docs/security/sub/v1.md（子目錄）、docs/security/v3.0.md.txt（副檔名）
  - docs/security/v4.0.md（值尾多一字元 ...e6c307X）
  - docs/security/v5.0.md（9f3a0123c456789e7b2d，非 0123 開頭）
  - docs/security/v2.0.md（隨機 32 位 hex api_key）
  - docs/security/v6.0.md（aws-access-token AKIA...）
對照：用 develop 的 .gitleaks.toml 掃同一 repo，v0.9.0.md 與 v1.0.md 也被抓，證明放行來自本 PR 規則。

## 4. 其他
- `uv run pytest -q tests/unit/test_gitleaks_allowlist.py`：26 passed
- `pre-commit run --all-files`：全部 Passed（trailing whitespace、eof、yaml、ruff、ruff format、bandit）
- 判定誤判合理：值為 0123…456789 順序假值。
- 備註（非 FAIL）：派工單背景值與實際被抓值不同，兩者皆符合同形狀，已涵蓋。

問題數量：0
