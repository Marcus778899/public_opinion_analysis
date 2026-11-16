PASS eb2e33c

驗證項目與原始輸出摘要（自己執行）：

1. 只改 .gitleaks.toml：`git diff $(git merge-base develop HEAD) HEAD --stat` -> `.gitleaks.toml | 10 ++++++++++`（只新增 10 行）。
2. 規則範圍：targetRules=generic-api-key、condition=AND、paths `^tests/`、regexTarget=secret、值 `^0123[0-9a-f]{0,6}456789[0-9a-f]{0,6}$`，有理由註解；未排除整個路徑、未關規則、無 fingerprint。
3. `gitleaks git --log-opts="develop..feat/bbs-retest-tool" --config .gitleaks.toml` -> `3 commits scanned ... no leaks found`。
   對照：同指令改用 develop 版 .gitleaks.toml -> `leaks found: 1`（確認原本確實被擋，修正有效）。
4. 全歷史 `gitleaks git --config .gitleaks.toml` -> `534 commits scanned ... no leaks found`。
5. 反例（$TMPDIR 暫存 repo，已刪）：
   - tests/unit/ok.py 的 `0123abc456789def` 被放行（預期）。
   - 仍被抓到（共 9 筆）：src/a.py 與 docs/c.md 同值 `0123abc456789def`（不在 tests/）；tests/ 內 `a1b2c3d4e5f6a7b8c9d0`、`9f3c2a7b1d4e8f60`（其他 hex）、`0123abc456789defAB`（大寫）、`xx0123abc456789def`（前綴）、`0123abc45678def`（缺 456789）、`0123abc456789def0123456789abcdef`（過長）；aws-access-token 規則在 tests/ 仍作用。
6. `pre-commit run --all-files` -> 全部 Passed（trailing whitespace、end of files、yaml、ruff、ruff format、bandit；gitleaks 不在 pre-commit 內，已另跑）。

備註（minor，不影響判定）：註解寫「10～22 位」，regex 實際為 10～16 位（4+0..6+6+0..6）。建議順手改註解，發版前 security 追認。
