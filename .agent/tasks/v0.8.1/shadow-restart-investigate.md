# 派工單 shadow-restart-investigate

- **類型**：chore
- **負責**：backend
- **目標**：查出 `inference-shadow`（ckip fp32）啟動後反覆重啟、沒有進度的原因，回報證據與建議的修法（本單只調查，不改程式）
- **背景**：2026-10-28 10:30Z 甲方設 `INFERENCE_SHADOW_MODEL_VERSION=bert-ckip-202610280849` 並啟動 shadow（`--profile app --profile shadow up -d --wait inference-shadow`）。log 每約 45 秒出現一次「loaded 18 post hashes from clickhouse」「inference shadow with …」，之間沒有任何錯誤或 traceback，hash 一直是 18（沒進度）。甲方 `docker inspect`：`OOMKilled=false`、`RestartCount=11`；容器內 `/sys/fs/cgroup/memory.peak` 1316524032、`memory.events` oom_kill 0；`docker stats` 約 815 MiB／1.5 GiB。manager 已 `stop` 該容器。7.27 的預期是補資料期間每批 100 篇（`INFERENCE_MAX_BATCH_TOKENS` 4096 分小批），evaluate 在主機量到峰值 932 MB、每批 p50 25.8 s。可能方向（未驗證）：healthcheck、Kafka `max.poll.interval.ms`／session timeout、process 被 SIGKILL 但未記為 OOM、Docker Desktop VM 記憶體
- **設計依據**：`docs/development-spec.md` 7.27（shadow 表、「評估結果與進 shadow 的調整」順序 6 觀察表）；D-023
- **相依**：無
- **負責檔案**：無（只寫回報檔；不改 repo 內任何檔案）
- **禁區**：不改程式、compose、`.env`；不刪 volume、不動 primary `inference` 與其他服務；只用 `docker compose -f infra/docker-compose.yaml --env-file .env --profile app --profile shadow …`（up／logs／ps／exec／stats／stop）；調查完把 `inference-shadow` stop
- **驗收測試**：無
- **驗收條件**：
  - [ ] 回報寫明每次結束的原因與證據（例：退出碼、收到的訊號、healthcheck 狀態、Kafka consumer group 狀態、記憶體時間序列），區分「確認」與「推測」
  - [ ] 提出修法選項與各自影響（程式、設定、compose、或照 7.27 順序 4 截到 256），標明哪些屬於決策分級（例：放寬 D-023）
  - [ ] 結束時 `inference-shadow` 已 stop，primary `inference` 仍在運作
- **驗證指令**：`docker compose -f infra/docker-compose.yaml --env-file .env --profile app --profile shadow ps -a`
- **回報檔**：`reports/shadow-restart-investigate.json`

## 執行資訊（task.py 產生）

- Issue：#201
- 分支：`chore/shadow-restart-investigate`（從 develop 開出）
- 工作目錄：`.worktrees/shadow-restart-investigate`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
