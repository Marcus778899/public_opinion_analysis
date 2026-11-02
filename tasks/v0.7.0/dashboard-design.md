# 派工單 dashboard-design

- **類型**：docs
- **負責**：architect
- **目標**：階段 7 Dashboard 的呈現方式評估與設計（S7-01、S7-02）
- **背景**：開發規格原定 Grafana＋ClickHouse datasource；甲方想比較「全用 Grafana 面板」與「Grafana 只做監控＋自建 web 前端」兩案，由你評估後列成待決定（範圍＋新技術棧，決策①②）。評估要寫各案的工作量、相依與維運成本、能否滿足 S7-02 面板與 `make up` 免手動設定的驗收；選 web 前端時，後續會另派 designer 出畫面規格
- **設計依據**：`docs/development-spec.md` 階段 7；`docs/realtime-sentiment-radar-design.md`（ClickHouse 表、警示）；`infra/clickhouse/`；`infra/docker-compose.yaml`
- **相依**：無
- **負責檔案**：
  - `docs/development-spec.md`
  - `docs/realtime-sentiment-radar-design.md`
- **禁區**：不改程式、compose、Grafana provisioning（骨架等甲方選定方案後再補）；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 兩案比較（工作量、相依、維運、驗收可達性）與建議，寫進設計文件或開發規格階段 7
  - [ ] 依建議案列出查詢來源（ClickHouse 表／view）、面板清單與實作派工順序（task_id、負責、負責檔案、驗收測試目錄）
  - [ ] 「需調查」「待決定」「自行決定」分開列在回報
- **驗證指令**：`git diff --stat develop`
- **回報檔**：`reports/dashboard-design.json`

## 執行資訊（task.py 產生）

- Issue：#85
- 分支：`docs/dashboard-design`（從 develop 開出）
- 工作目錄：`.worktrees/dashboard-design`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
