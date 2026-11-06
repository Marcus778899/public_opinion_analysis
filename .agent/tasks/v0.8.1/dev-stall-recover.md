# 派工單 dev-stall-recover

- **類型**：chore
- **負責**：backend
- **目標**：開發環境停擺：先保留證據，再恢復 kafka_1、`radar-cdc` connector、scheduler，最後查清原因並提出修法。不改程式
- **背景**：2026-11-04 約 03:15Z manager 看 log 發現三件事：
  1. kafka_1 unhealthy，最後一行 log 停在 2026-11-03 17:38Z；16:39Z 起連不到 node 2、3（`SocketTimeoutException: Failed to connect within 30000 ms`）、heartbeat 送不出。kafka_2 healthy；kafka_3 在 03:01Z 重啟過。
  2. cdc-watchdog 從 03:04Z（或更早）每 30 秒報 `connector radar-cdc not found`；connect 03:12Z 重啟後仍然 404。
  3. scheduler 每次送 `crawl.tasks` 都失敗：`KafkaError{code=_FATAL,val=-150,"Local: Fatal error"}`（`radar/common/kafka/producer.py:56`，DuePostDispatcher 和 send_list_task 都是），Kafka 恢復後不會自己好。
  ingest、crawler 正常（crawler 在消化 11-03 11:40～12:04Z 的舊任務）。甲方同意先恢復再查原因；scheduler 的修正不在本單實作。
- **設計依據**：開發規格 7.16（CDC 故障自動恢復）、7.28 B（`cdc-watchdog`）、7.20；D-034（Kafka 4.1.2）；`tools/register_connector.py`（`make connector`）
- **相依**：無
- **負責檔案**：
  - `.agent/reports/dev-stall-recover.json`
- **禁區**：不改任何程式、設定與資料；不刪 volume、不 `down -v`、不刪 topic 或 consumer group；只用 `docker compose -p radar restart <服務>` 或 `docker compose -f infra/docker-compose.yaml --env-file .env up -d <服務>` 這類可還原的動作；不可讀 `.env`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 恢復前先存證據：kafka_1、kafka_2、kafka_3、connect、scheduler、cdc-watchdog 從 2026-11-03 16:00Z 起的 log 摘要（起點、關鍵錯誤、時間點）寫進回報；`docker compose -p radar ps` 輸出
  - [ ] 恢復 kafka_1：重啟後三台 healthy，`kafka-topics --describe --under-replicated-partitions` 沒有結果
  - [ ] 恢復 `radar-cdc`：註冊後 `GET /connectors/radar-cdc/status` connector 與 task 都是 RUNNING，cdc-watchdog 不再報 not found。sandbox 讀不到 `.env` 而無法註冊時，停下來在回報寫出甲方要在自己終端機跑的指令
  - [ ] 恢復 scheduler：重啟後 log 沒有 `_FATAL`，`crawl.tasks` 有新任務送出（附 log 或 offset）
  - [ ] 原因分析，分成「環境（休眠、網路）」「Kafka／Debezium 問題」「程式問題」，附證據：kafka_1 為什麼卡住、是不是開發機休眠；`radar-cdc` 為什麼不見（connect_configs topic、connect 重啟、誰刪的）；scheduler 遇到 `_FATAL` 為什麼沒有重建 producer 或結束程式交給 restart policy
  - [ ] 程式有問題的話，寫下重現條件與建議的修法（寫在回報，不實作）
- **驗證指令**：回報附上實際執行的指令與輸出
- **回報檔**：`.agent/reports/dev-stall-recover.json`

## 執行資訊（ae task 產生）

- Issue：#280
- 分支：`chore/dev-stall-recover`（從 develop 開出）
- 工作目錄：`.worktrees/dev-stall-recover`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
