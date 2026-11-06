# 派工單 kafka-rolling-restart

- **類型**：chore
- **負責**：backend
- **目標**：開發環境的 kafka_1～3 逐台重建，讓 PR #286（Kafka 對外 port 改綁 127.0.0.1，D-039）生效；重建後確認依賴 Kafka 的服務都正常。不改程式
- **背景**：PR #286 已合併到 develop，主目錄的 `infra/docker-compose.yaml` 已是新設定，但執行中的三台 Kafka 還是舊容器（綁 0.0.0.0）。甲方 2026-11-04 授權直接做。上次 kafka_1 卡住時 connect 啟動卡住（內部 topic RF=1，#282）、scheduler 的 producer 進入 fatal 不會自己好（#281），見 `.agent/reports/dev-stall-recover.json`。
- **設計依據**：D-039；D-034（Kafka 4.1.2）；`.agent/reports/dev-stall-recover.json` 的恢復步驟
- **相依**：無
- **負責檔案**：
  - `.agent/reports/kafka-rolling-restart.json`
- **禁區**：不改程式、設定、`.env`（不可讀 `.env`）；不 `down`、不刪 volume、不刪 topic 或 consumer group；一次只重建一台 Kafka，前一台 healthy 且沒有 under-replicated 才換下一台；除了 kafka_1～3 以外只允許 restart（不重建）connect、scheduler、heat、bot、ingest、crawler
- **驗收測試**：無
- **驗收條件**：
  - [ ] 重建前記下 `docker compose -p radar ps` 與 Kafka ports（應為 0.0.0.0）
  - [ ] 依序 `docker compose -f infra/docker-compose.yaml --env-file .env up -d --no-deps <kafka_N>`（N=1、2、3）；每台之後等 healthy，`kafka-topics.sh --describe --under-replicated-partitions` 沒有結果才繼續（在容器內用 `--bootstrap-server localhost:29092`）
  - [ ] 三台都重建後 `docker compose -p radar ps` 顯示 `127.0.0.1:9092->9092`、`127.0.0.1:9094->9094`、`127.0.0.1:9096->9096`
  - [ ] connect：`radar-cdc` connector 與 task 都 RUNNING；scheduler、crawler、ingest、heat、bot 的 log 重建後沒有 `_FATAL`／ERROR 持續出現，`crawl.tasks` 有新任務、ingest 有寫入、heat lag 接近 0；有卡住就照 dev-stall-recover 的方式 restart 該服務並記錄
  - [ ] 主機上的工具還連得上：`uv run python -c` 用 `localhost:9092` 列出 topic（或等效的唯讀查詢）
- **驗證指令**：回報附上實際執行的指令與輸出
- **回報檔**：`.agent/reports/kafka-rolling-restart.json`

## 執行資訊（ae task 產生）

- Issue：#287
- 分支：`chore/kafka-rolling-restart`（從 develop 開出）
- 工作目錄：`.worktrees/kafka-rolling-restart`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
