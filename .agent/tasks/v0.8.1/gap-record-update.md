# 派工單 gap-record-update

- **類型**：docs
- **負責**：backend
- **通道**：fast
- **目標**：開發規格 7.29 補上 2026-10-30 的停機缺口（D-032）
- **背景**：reports/comments-cdc-gap-investigate.json：2026-10-30 04:05Z～07:15Z 開發機合蓋休眠約 3.2 小時，爬蟲源頭就沒有產出。Debezium 從上次的 LSN 續跑，PG 與 ClickHouse 的 posts 一致。cdc-watchdog 在 05:06 記了 ERROR，但當時沒有網路，`/fail` 沒送出去；恢復後的 6 則警示是失真結果（7.20 已知限制，#264）。
- **設計依據**：D-032；開發規格 7.29；reports/comments-cdc-gap-investigate.json
- **相依**：無
- **負責檔案**：
  - `docs/development-spec.md`（只限 7.29）
- **禁區**：不改其他章節、程式
- **驗收測試**：無
- **驗收條件**：
  - [ ] 7.29 表格加第 10 列（區間、長度、原因），標題的日期範圍延到 10-30
  - [ ] 補一行說明：watchdog 有記 ERROR，但沒網路所以 `/fail` 沒送出；恢復後的警示是失真的，見 #264
  - [ ] 數字以調查回報為準，附上出處
- **驗證指令**：`pre-commit run --files docs/development-spec.md`
- **回報檔**：`reports/gap-record-update.json`

## 執行資訊（task.py 產生）

- Issue：#266
- 分支：`docs/gap-record-update`（從 develop 開出）
- 工作目錄：`.worktrees/gap-record-update`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
