# 派工單 comments-cdc-gap-investigate

- **類型**：chore
- **負責**：backend
- **目標**：查清 2026-10-30 04:30Z～07:15Z 約 3 小時 `cdc.public.comments` 沒有事件的原因，以及 #224 的停擺警告有沒有發出。只調查、不改程式
- **背景**：UAT v0.8.1 F-3（docs/uat/v0.8.1.md）。這段期間 connect 多次出現 `Producer failure` 重試；恢復後 07:28～07:32Z 連發 6 則警示。07:25Z manager 有重新部署（重建 postgres、clickhouse 與 app 容器，connect 和 kafka 沒重建）。甲方在部署前用 ALTER USER 改過 PG 密碼。
- **設計依據**：開發規格 7.16（CDC 故障自動恢復）、7.28 B（`cdc-watchdog`）、D-034（Kafka 4.1.2）
- **相依**：無
- **負責檔案**：
  - `reports/comments-cdc-gap-investigate.json`
- **禁區**：不改任何程式、設定與資料；不重啟、不停止任何容器；查詢只讀（`docker compose ... exec` 下唯讀查詢、`docker compose ... logs`；log 在 `log/`）
- **驗收測試**：無
- **驗收條件**：
  - [ ] 列出這段時間 PG `comments`、`posts` 有沒有新資料（爬蟲和 ingest 是否正常），以及 ClickHouse 有沒有收到
  - [ ] 從 connect、kafka_1～3、ingest、crawler、cdc-watchdog 的 log 找出停擺的起點、原因與恢復的時間點，附上證據；分成「環境（休眠、網路）」「Kafka／Debezium 問題」「程式問題」
  - [ ] `cdc-watchdog` 在這段時間有沒有記 ERROR、heartbeat 有沒有送 `/fail`；沒有的話，說明原因
  - [ ] 07:28～07:32Z 那 6 則警示，判斷是不是停擺後一次湧入資料造成的誤報
  - [ ] 程式有問題的話，寫下重現條件與建議的修法（寫在回報，不實作）
- **驗證指令**：回報附上實際執行的查詢、指令與輸出
- **回報檔**：`reports/comments-cdc-gap-investigate.json`

## 執行資訊（task.py 產生）

- Issue：#260
- 分支：`chore/comments-cdc-gap-investigate`（從 develop 開出）
- 工作目錄：`.worktrees/comments-cdc-gap-investigate`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
