# 派工單 gitleaks-test-sentinel

- **類型**：chore
- **負責**：architect
- **通道**：scan
- **目標**：先確認 gitleaks 擋 `bbs-spike-tool` 是誤判，是的話在 `.gitleaks.toml` 加窄規則放行測試裡的哨兵假密碼
- **背景**：
  - `ae pr open bbs-spike-tool` 的推送前掃描報 `generic-api-key`：`tests/unit/acceptance/bbs-spike-tool/test_bbs_spike_acceptance.py` 第 20 行（commit 4a52f42），`SECRET_PW = "S3ntinel-pw-9f2c"`，是驗收測試用來驗「密碼不外洩」的哨兵值
  - 驗收測試已鎖定，且 gitleaks 掃歷史，改測試解決不了；照 D-018、D-026 的方式加窄規則，不逐筆加 fingerprint、不排除整個路徑
  - 確認不是誤判（例：其實是真帳密）就停下回報，不改設定
- **設計依據**：CLAUDE.md 決策分級④（掃描誤判）；`.gitleaks.toml` 既有規則；D-018、D-026
- **相依**：無
- **負責檔案**：
  - `.gitleaks.toml`
- **禁區**：不改測試與程式；不排除整個路徑或關掉規則
- **驗收測試**：無
- **驗收條件**：
  - [ ] 規則只放行可辨識的測試哨兵（例：值含 `sentinel`、限 `tests/` 路徑），設定裡附理由
  - [ ] 證明：`bbs-spike-tool` 分支的掃描通過，且同樣格式的真密鑰（不含哨兵特徵、或在 `tests/` 以外）仍被抓到；附實際指令與輸出
- **驗證指令**：`gitleaks git --log-opts="origin/develop..feat/bbs-spike-tool" --config .gitleaks.toml`；`make check`
- **回報檔**：`.agent/reports/gitleaks-test-sentinel.json`

## 執行資訊（ae task 產生）

- Issue：#322
- 分支：`chore/gitleaks-test-sentinel`（從 develop 開出）
- 工作目錄：`.worktrees/gitleaks-test-sentinel`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
