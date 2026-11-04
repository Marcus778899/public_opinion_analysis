# 派工單 heat-replay-cleanup

- **類型**：chore
- **負責**：backend
- **目標**：清掉開發環境 Kafka 遺留的 `heat-replay-*` consumer group 與 Quix 內部 topic（D-038），確認沒有殘留的回放 heat 程序。不改程式
- **背景**：UAT v0.8.1 回放測試（開發規格 7.20）留下約 6 組 `heat-replay-<epoch>` consumer group 與 changelog、repartition 內部 topic（名稱含 group 名，例 `changelog__heat-replay-1793347268--…`、`repartition__heat-replay-1793347268--…`，另有不帶 epoch 的 `heat-replay`）。甲方 2026-11-04 決定清掉（D-038）。UAT 當時在自動模式下批次刪除被擋。初測時另有一個回放 heat（PID 74977）沒能確認是否已結束。
- **設計依據**：D-038；開發規格 7.20「做完要清」
- **相依**：無
- **負責檔案**：
  - `.agent/reports/heat-replay-cleanup.json`
- **禁區**：只刪名稱含 `heat-replay` 的 consumer group 與 topic；不可刪 `replay.cdc.comments`、`replay.alerts`（7.20 會重建使用）、正式 `heat` 的 group 與它的 changelog／repartition（名稱是 `heat--…`，不含 `replay`），其他 topic、group 一律不動；不改程式、設定；不讀 `.env`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 刪之前列出要刪的 group 與 topic 清單（附 `kafka-consumer-groups.sh --list`、`kafka-topics.sh --list` 過濾後的輸出），確認每一個名稱都含 `heat-replay`、group 都沒有活著的成員
  - [ ] 刪除後同樣兩個指令再列一次，沒有 `heat-replay`；正式 `heat`、`ingest`、`crawler` 等 group 與 `replay.cdc.comments`、`replay.alerts` 仍在
  - [ ] 確認主機上沒有在跑的回放 heat（PID 74977 或任何 `radar.streaming.heat` 本機程序）；sandbox 看不到程序清單時，在回報寫出甲方要跑的指令
  - [ ] 刪除被自動模式擋下時停下來，不要換方法繞過；在回報寫出甲方在自己終端機要跑的完整指令
- **驗證指令**：回報附上實際執行的指令與輸出
- **回報檔**：`.agent/reports/heat-replay-cleanup.json`

## 執行資訊（ae task 產生）

- Issue：#284
- 分支：`chore/heat-replay-cleanup`（從 develop 開出）
- 工作目錄：`.worktrees/heat-replay-cleanup`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
