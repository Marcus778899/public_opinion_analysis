# 派工單 ci-tool-checksum

- **類型**：chore
- **負責**：backend
- **目標**：CI 下載 gitleaks、osv-scanner 執行檔後先驗證 SHA-256，對不上就讓 CI 失敗（#70）
- **背景**：來源資安 v0.6.0 L-2。`.github/workflows/ci.yml` 的 Security job 用 curl 下載執行檔後直接執行。版本號已經是變數（`GITLEAKS_VERSION`、`OSV_SCANNER_VERSION`）。
- **設計依據**：#70；docs/security/v0.6.0.md L-2
- **相依**：無
- **負責檔案**：
  - `.github/workflows/ci.yml`（只限 Security job 的下載步驟與版本、checksum 變數）
- **禁區**：不改其他 job、不換工具版本、不改 gitleaks／osv-scanner 的掃描設定與忽略清單
- **驗收測試**：無
- **驗收條件**：
  - [ ] 兩個執行檔下載後都會先比對寫死的 SHA-256；對不上時那一步失敗、CI 變紅
  - [ ] checksum 要從官方 release 頁或官方 checksums 檔取得，回報附上來源網址與實際比對的輸出
  - [ ] 推上 PR 後 CI 的 Security job 是綠的
- **驗證指令**：在本機用同樣的指令下載並比對（`sha256sum -c` 或 `shasum -a 256 -c`），附上輸出
- **回報檔**：`reports/ci-tool-checksum.json`

## 執行資訊（task.py 產生）

- Issue：#237
- 分支：`chore/ci-tool-checksum`（從 develop 開出）
- 工作目錄：`.worktrees/ci-tool-checksum`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
