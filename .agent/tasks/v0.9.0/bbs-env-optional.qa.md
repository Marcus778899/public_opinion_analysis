PASS a604ab1

驗證（worktree .worktrees/bbs-env-optional，自己執行）：

- `grep -nE "^PTT_BBS_" .env.example` -> 無輸出，exit 1（符合）
- `uv run pytest tests/unit/acceptance/bbs-env-optional tests/unit/acceptance/bbs-spike-tool -q` -> `88 passed in 0.70s`
- `make check` -> `2246 passed in 142.77s`（含 ruff、其餘單元測試）
- `grep -rn "TODO(bbs-env-optional)" src tests` -> 無結果

驗收條件：
- [x] `.env.example` 兩個變數為 `# PTT_BBS_USERNAME=`、`# PTT_BBS_PASSWORD=`，無值，段落說明改引用 D-050
- [x] 驗收測試全過、make check 通過；舊測試已改為斷言註解形式；新測試涵蓋工具在變數未設或為空字串時拒絕登入且只提變數名稱
- [x] 開發規格 7.31 G-6 該列寫明已依 D-050 改回選填、`bbs-env-isolation` 不做

禁區：diff 只動 `.env.example`、`docs/development-spec.md`、兩個驗收測試檔；未動 `tools/bbs_spike.py`、compose、check-env。
未跑整合測試（只改範例檔與文件，合理）。無寫死設定值。

備註（非 FAIL）：開發規格 G-a 待決定列（約 2162 行）仍寫「推翻 D-046」的選項表，與 G-6 已更新一致（採 A），不影響結論。
