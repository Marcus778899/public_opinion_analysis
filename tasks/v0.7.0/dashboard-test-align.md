# 派工單 dashboard-test-align

- **類型**：docs
- **負責**：architect
- **目標**：修訂開發規格 7.25 的測試做法，配合 7.26（整合測試改走 compose `test` 服務、移除 testcontainers、xdist 平行）
- **背景**：7.25 的 `test_grafana_infra.py`（離線重啟沿用 volume）與 `dashboard-integration`（testcontainers 開 Grafana）在 7.26 之後做不到；7.26 做法 1 的服務清單沒有 grafana；唯讀帳號 `allow_databases` 只有 `radar`，與 xdist 的 worker DB 衝突。architect 已提出修法：grafana 加進 `compose.yaml`（internal 網路＝每次都是離線啟動）、`IT_GRAFANA_URL`、唯讀查詢一律用 `radar` DB、`dashboard-grafana-infra` 排在 `test-infra-compose` 之後並擴充負責檔案
- **設計依據**：`docs/development-spec.md` 7.25、7.26；D-014、D-015
- **相依**：無（`test-infra-compose` 也改本檔 1.1、1.3、5 章與 7.26 狀態，本單只動 7.25 與 7.26 做法 1 的服務清單）
- **負責檔案**：
  - `docs/development-spec.md`
- **禁區**：不改程式、compose、CI；不改 7.26 除做法 1 服務清單以外的內容
- **驗收測試**：無
- **驗收條件**：
  - [ ] 7.25 派工順序表（`dashboard-grafana-infra`、`dashboard-views`、`dashboard-integration` 列）與 `test_grafana_infra.py` 表依上述修法改寫，不再出現 testcontainers
  - [ ] 7.26 做法 1 服務清單補上 grafana；CI 覆寫檔與離線檢查的限制寫明
  - [ ] 回報列出「自行決定」變更；不涉及新的待決定
- **驗證指令**：`grep -n "testcontainers" docs/development-spec.md`
- **回報檔**：`reports/dashboard-test-align.json`

## 執行資訊（task.py 產生）

- Issue：#92
- 分支：`docs/dashboard-test-align`（從 develop 開出）
- 工作目錄：`.worktrees/dashboard-test-align`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
