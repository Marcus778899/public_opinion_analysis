# 派工單 gitleaks-hash-key-fixture

- **類型**：chore
- **負責**：architect
- **通道**：scan
- **目標**：`bbs-retest-tool` 的推送前 gitleaks 檢查被測試資料擋下（generic-api-key），確認是誤判後在忽略設定加窄規則
- **背景**：
  - 被擋的位置：分支 `feat/bbs-retest-tool` commit b8018db，`tests/unit/acceptance/bbs-retest-tool/test_bbs_retest_acceptance.py` 第 829 行，測試資料 `{"key": "0123abc456789def"}`（測短帳號夾在雜湊鍵裡不算洩漏，G-4 O-2）
  - 掃描範圍含歷史 commit，改測試檔無法讓檢查通過
  - 既有前例：`gitleaks-test-sentinel`（PR #323）只放行 `tests/` 底下 `s[e3]ntinel[-_]` 開頭的值；D-018、D-026 是同類窄規則
  - 若判定不是誤判（真的密鑰），停下回報，不改設定
- **設計依據**：CLAUDE.md 決策分級④（掃描誤判可加窄規則、附理由、證明同格式真密鑰仍會被抓）；`.gitleaks.toml` 既有規則
- **相依**：無
- **負責檔案**：
  - `.gitleaks.toml`
- **禁區**：只改 `.gitleaks.toml`；不排除整個路徑、不關規則；不動 `.worktrees/bbs-retest-tool`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 規則只放行這一類測試資料（路徑、規則、值的格式都要限縮），附理由註解
  - [ ] 對 `feat/bbs-retest-tool` 的 commit（`develop..feat/bbs-retest-tool`）跑 gitleaks 0 筆
  - [ ] 證明同格式但不在測試目錄、或不同值格式的真密鑰仍會被抓到（附指令與輸出）
- **驗證指令**：`gitleaks git --log-opts="develop..feat/bbs-retest-tool" --config .gitleaks.toml`；`pre-commit run --all-files`
- **回報檔**：`.agent/reports/gitleaks-hash-key-fixture.json`

## 執行資訊（ae task 產生）

- Issue：#333
- 分支：`chore/gitleaks-hash-key-fixture`（從 develop 開出）
- 工作目錄：`.worktrees/gitleaks-hash-key-fixture`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
