# 派工單 bbs-env-optional

- **類型**：chore
- **負責**：backend
- **目標**：依 D-050 把 `.env.example` 的 `PTT_BBS_USERNAME`、`PTT_BBS_PASSWORD` 改回選填（寫成註解，照 D-009），讓 `ae check-env` 不再要求填值
- **背景**：
  - D-050：補實驗報告（PR #337）已合併，D-046 失效；改回註解後甲方清空 `.env` 的值並改小號密碼（甲方自己做，不在本單）
  - 既有驗收測試 `tests/unit/acceptance/bbs-spike-tool/test_bbs_spike_acceptance.py` 的 `test_env_example_ptt_bbs_vars_are_uncommented_with_empty_values` 鎖的是 D-046 的舊契約，由 qa「A」依 D-050 改寫成「兩個變數都是註解、沒有值」
  - `tools/bbs_spike.py` 照舊只從環境變數讀；沒設時工具要照現有行為拒絕登入（不改程式邏輯）
  - `bbs-env-isolation` 不做（D-050，留 backlog）
- **設計依據**：D-009、D-046、D-050；開發規格 7.31 G-6、G-10 的 G-a
- **相依**：無
- **負責檔案**：
  - `.env.example`（只動 PTT BBS 那一段）
  - `docs/development-spec.md`（只動 7.31 G-6 那一列：寫明已依 D-050 改回選填、`bbs-env-isolation` 不做）
  - `tests/unit/acceptance/bbs-spike-tool/test_bbs_spike_acceptance.py`（只由 qa「A」改寫上述那個測試）
- **禁區**：不改 `tools/bbs_spike.py`、compose、check-env 工具；不讀 `.env`
- **驗收測試**：
  - `tests/unit/acceptance/bbs-env-optional/`
  - `tests/unit/acceptance/bbs-spike-tool/test_bbs_spike_acceptance.py`
- **驗收條件**：
  - [ ] `.env.example` 兩個變數都改成註解（`# PTT_BBS_USERNAME=`、`# PTT_BBS_PASSWORD=`），沒有值，段落說明改引用 D-050
  - [ ] 驗收測試全過，`make check` 通過
  - [ ] 開發規格 7.31 G-6 更新
- **驗證指令**：`make check`；`grep -nE "^PTT_BBS_" .env.example` 沒有結果
- **回報檔**：`.agent/reports/bbs-env-optional.json`

## 執行資訊（ae task 產生）

- Issue：#338
- 分支：`chore/bbs-env-optional`（從 develop 開出）
- 工作目錄：`.worktrees/bbs-env-optional`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
