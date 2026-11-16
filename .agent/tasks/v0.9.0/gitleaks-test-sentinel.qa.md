PASS 5471190

驗證項目與原始輸出摘要（自行執行）：

1. 加規則前（用主目錄 .gitleaks.toml）掃 `origin/develop..feat/bbs-spike-tool`：`leaks found: 1`（確認為誤判：SECRET_PW="S3ntinel-pw-9f2c"，驗收測試的哨兵值）。
2. 加規則後 `gitleaks git --log-opts="origin/develop..feat/bbs-spike-tool" --config .gitleaks.toml --redact`：`2 commits scanned. no leaks found`。
3. 全歷史 `gitleaks git --config .gitleaks.toml --redact`：`508 commits scanned ... no leaks found`。
4. 反例（`$TMPDIR/glq`，不在 repo 內，`gitleaks dir . --config <worktree>/.gitleaks.toml`）：
   - 放行：tests/unit/ok.py（S3ntinel-pw-9f2c）、tests/unit/ok2.py（sentinel_account_77x）
   - 仍抓到（共 6 個，leaks found: 6）：tests/ 內非哨兵 Qx7rTmb-pw-9f2c、tests/ 內 API_KEY、tests/ 內 password、tests/ 內 xsentinel-（非開頭）、src/tests/ 內哨兵值、other/ 內哨兵值
5. 規則範圍：單一 allowlist，targetRules=generic-api-key、condition=AND、paths ^tests/、regexTarget=secret、(?i)^s[e3]ntinel[-_]；有理由註解；未排除整個路徑、未關規則、未逐筆 fingerprint。僅改 .gitleaks.toml（10 行新增）。
6. `pre-commit run --all-files`：全部 Passed；`uv run pytest tests/unit -n auto`：2023 passed。

備註（非問題）：任何放在 tests/ 且以 sentinel-／s3ntinel- 開頭的值都會被放行，屬設計取捨，發版前由 security 追認。
