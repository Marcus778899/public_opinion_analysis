# 派工單 pipeline-gap-design

- **類型**：docs
- **負責**：architect
- **目標**：設計兩個修正並記下歷史缺口：①爬蟲重啟後補抓深度不足 ②資料管線靜默停擺（容器都 Up 但沒新資料）時要發警告；③依 D-032 在開發規格記下 10-08～10-28 的停機缺口
- **背景**：調查見 `reports/gossiping-gap-investigate.json`（#180）：重啟後 `handle_list` 只抓第一頁、上限 `max_list_pages=3`，Gossiping、HatePolitics 漏約 1 萬篇；10-28 16:18Z 起 kafka_3 group coordinator 異常（Kafka 4.1.0）使管線停 10 小時，容器都 Up、沒有任何警告（manager 重啟 kafka_3 後恢復）
- **設計依據**：`docs/development-spec.md` 7.10、7.12、7.16（cdc-watchdog）、7.17、7.22；D-032；CLAUDE.md「資料與架構約定」（爬蟲不碰 PG 等）
- **相依**：無
- **負責檔案**：
  - `docs/development-spec.md`（新增設計補充小節、第 6 章與風險清單的對應更新、停機缺口紀錄）
  - `docs/realtime-sentiment-radar-design.md`（行為有變時同步）
- **禁區**：不寫實作程式；對真實 PTT 的請求量增加要估算並設上限（#11 被擋的風險）；新增套件、付費服務、對外通知管道的變更屬決策分級，列「待決定」
- **驗收測試**：無
- **驗收條件**：
  - [ ] 補抓：重啟或停擺後如何決定要往前翻幾頁（資訊從哪來、誰查 PG、任務訊息格式是否變更、硬上限與請求量估算）
  - [ ] 停擺偵測：偵測什麼訊號（例：各看板最新資料時間、consumer lag、coordinator 錯誤）、門檻、由哪個服務做、如何通知（沿用 cdc-watchdog 的 email 或其他）；Kafka 4.1.0 這個錯誤是否需要升級（列需調查）
  - [ ] 開發規格記下停機缺口日期（D-032）
  - [ ] 實作派工順序（task_id、負責、可否平行、負責檔案、驗收測試目錄）；「需調查」「待決定」「自行決定」三張表
- **驗證指令**：無（文件）
- **回報檔**：`reports/pipeline-gap-design.json`

## 執行資訊（task.py 產生）

- Issue：#219
- 分支：`docs/pipeline-gap-design`（從 develop 開出）
- 工作目錄：`.worktrees/pipeline-gap-design`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
