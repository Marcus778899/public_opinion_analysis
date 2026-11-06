# 派工單 stability-dev-verify

- **類型**：chore
- **負責**：backend
- **目標**：在開發環境部署 develop 最新版，實測 v0.8.2 的驗收條件：停任一台 broker 時 connect 照樣啟動且 connector 還在、推論在資源上限內補完積壓、重建 postgres 後 init 一次成功、producer fatal／結束後被 docker 重啟並恢復送訊息；只操作，不改程式，PR 作廢
- **背景**：
  - producer-fatal-exit、connect-resilience、backfill-since-filename、inference-resource-limit 已合併，connect-rf-reassign 已完成（3 個內部 topic RF=2、min.isr=1）
  - 部署：照 Makefile `up-app`、`up-inference` 的寫法直接下 `docker compose -f infra/docker-compose.yaml --env-file .env --profile app up -d --build --wait`（推論再加 `--profile inference up -d --wait inference`）；shadow 不開（D-040）
  - 停 broker 演練一次只停一台，前一台 `--under-replicated-partitions` 清空才換下一台；任何一步不符預期就停下回報，先把停掉的 broker 啟動回來
- **設計依據**：`docs/development-spec.md` 7.30 B 步驟 7、C「驗證」、派工順序第 9 列；D-041、D-042
- **相依**：producer-fatal-exit、connect-resilience、backfill-since-filename、inference-resource-limit、connect-rf-reassign（都已完成）
- **負責檔案**：
  - 無（只操作開發環境，主目錄、專案 `radar`）
- **禁區**：不改 repo 檔案、不 commit；不刪 volume、不刪 topic、不重新註冊 connector；不開 shadow
- **驗收測試**：無
- **驗收條件**：
  - [ ] kafka_1、kafka_2、kafka_3 依序各一次：停掉 → `restart connect` → 3 分鐘內 `/health` 200、`/connectors/radar-cdc/status` RUNNING、`ps connect` healthy → 啟動回來、under-replicated 清空（附三台的輸出）
  - [ ] 推論停 ≥ 60 分鐘累積積壓後以新設定啟動：`memory.events` 的 `oom_kill` 為 0、`memory.peak` < 2g、consumer group `inference` lag 回到個位數、容器沒有重啟
  - [ ] `--profile app up -d --force-recreate --no-deps postgres`（volume 不動）後 `--profile app up -d --force-recreate --no-deps init` 第一次就 `Exited (0)`
  - [ ] scheduler 容器內 `kill -TERM 1` 後被 docker 重啟、`crawl.tasks` 的 offset 繼續增加
  - [ ] 結束時所有服務回到 running／healthy，回報附各項指令與輸出
- **驗證指令**：`docker compose -f infra/docker-compose.yaml --env-file .env ps`；各項見 7.30 B 步驟 7、C
- **回報檔**：`.agent/reports/stability-dev-verify.json`

## 執行資訊（ae task 產生）

- Issue：#307
- 分支：`chore/stability-dev-verify`（從 develop 開出）
- 工作目錄：`.worktrees/stability-dev-verify`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
