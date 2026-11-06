# 派工單 gossiping-gap-investigate

- **類型**：chore
- **負責**：backend
- **目標**：查清 Gossiping 在 10-19 等日期推文數幾乎為 0 的原因：開發環境停機，還是程式問題（#180）。只調查、不改程式
- **背景**：推文量調查（2026-10-26）發現；開發環境過去有停機紀錄（例：10/13 02Z～10/15 06Z，見開發規格第 6 章執行順序第 3 項）
- **設計依據**：#180；`docs/development-spec.md` 7.15（推文同步）、7.16（CDC 故障自動恢復）
- **相依**：無
- **負責檔案**：
  - `reports/gossiping-gap-investigate.json`
- **禁區**：不改任何程式、設定與資料；查詢只讀（ClickHouse、PG 用 `docker compose ... exec` 下唯讀查詢；log 在 `log/`）
- **驗收測試**：無
- **驗收條件**：
  - [ ] 列出近 30 天各看板每天的文章數、推文數（PG 與 ClickHouse 兩邊），標出異常日期
  - [ ] 每個異常日期的原因與證據：同時段其他看板是否正常、爬蟲／ingest／CDC log、容器重啟紀錄；分成「環境停機」「程式問題」「PTT 本身」
  - [ ] 若是程式問題：重現條件與建議的修正方向（寫在回報，不實作）；若資料可補回，說明怎麼補
- **驗證指令**：回報附上實際執行的查詢與輸出
- **回報檔**：`reports/gossiping-gap-investigate.json`

## 執行資訊（task.py 產生）

- Issue：#209
- 分支：`chore/gossiping-gap-investigate`（從 develop 開出）
- 工作目錄：`.worktrees/gossiping-gap-investigate`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
