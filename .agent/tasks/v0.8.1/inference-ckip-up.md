# 派工單 inference-ckip-up

- **類型**：chore
- **負責**：backend
- **目標**：開發環境啟動正式情緒推論 `inference`，使用甲方在 `.env` 設好的 `INFERENCE_MODEL_VERSION=bert-ckip-202610280849`（D-040），確認模型載入、推論結果正常寫出、記憶體與積壓可接受。不改程式
- **背景**：2026-11-04 發現 inference 與 shadow 都沒在跑；consumer group `inference` 沒有成員、lag 很大（`.agent/reports/kafka-rolling-restart.json`）。D-040：正式直接換 ckip fp32，shadow 不開。ckip 評估：每批 100 篇 p50 約 26 s、RSS 峰值 932 MB（開發規格「順序 3 判定」，`INFERENCE_THREADS=2`）；正式 inference 的 compose 沒設 mem_limit、threads。補積壓期間每批都是滿的。
- **設計依據**：D-040；開發規格 S4、第 8 章推論與「順序 3 判定」；Makefile `up-inference`（profile `app`＋`inference`）
- **相依**：無
- **負責檔案**：
  - `.agent/reports/inference-ckip-up.json`
- **禁區**：不改程式、設定、`.env`（不可讀 `.env`）；不開 shadow（`inference-shadow`）；不刪或重設 consumer group offset；除了 inference 以外不重建其他服務
- **驗收測試**：無
- **驗收條件**：
  - [ ] 啟動前記下 consumer group `inference` 的 lag 總數
  - [ ] `docker compose -f infra/docker-compose.yaml --env-file .env --profile app --profile inference up -d --wait inference` 啟動；log 顯示載入的 model_version 是 `bert-ckip-202610280849`，沒有 ERROR／traceback、沒有重啟迴圈
  - [ ] `predictions` topic 有新訊息、model_version 是 ckip（附一筆範例，不貼文章全文）；ClickHouse 有收到（附查詢與筆數）
  - [ ] 跑 10 分鐘以上：`docker stats` 的記憶體峰值、`docker inspect -f '{{.State.OOMKilled}}'`、每批耗時（log）、lag 下降速度，估計補完積壓要多久
  - [ ] 記憶體持續上升或被 OOM kill 時停下（`docker compose -p radar stop inference`），在回報寫原因與建議，不自行改設定
- **驗證指令**：回報附上實際執行的指令與輸出
- **回報檔**：`.agent/reports/inference-ckip-up.json`

## 執行資訊（ae task 產生）

- Issue：#288
- 分支：`chore/inference-ckip-up`（從 develop 開出）
- 工作目錄：`.worktrees/inference-ckip-up`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
