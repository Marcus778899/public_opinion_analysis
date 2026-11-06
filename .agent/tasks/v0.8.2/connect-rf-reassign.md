# 派工單 connect-rf-reassign

- **類型**：chore
- **負責**：backend
- **目標**：開發環境既有的 Connect 內部 topic（`connect_configs`、`connect_offsets`、`connect_statuses`）以 partition reassignment 改成 2 份副本、`min.insync.replicas=1`（#282、D-041）；只操作，不改程式，PR 作廢
- **背景**：
  - 甲方已核可 D-041：線上 reassignment，不刪資料、不重建 connector；先備份 connector config 與 offsets
  - 備份放 `$TMPDIR/connect-rf-backup/`，不進 repo、不貼進回報（config 含 PG 密碼），驗證完刪除含密碼的檔；回復檔（Current partition replica assignment）留著
  - 前置條件不符（broker 不健康、有 under-replicated、connector 不是 RUNNING）就停下回報，不要硬做
- **設計依據**：`docs/development-spec.md` 7.30 B「既有環境的操作步驟」0～6 與回復段落；D-041、D-042
- **相依**：connect-resilience（已合併）
- **負責檔案**：
  - 無（只操作開發環境，主目錄、專案 `radar`）
- **禁區**：不改 repo 檔案、不 commit；不做步驟 7 的停 broker 演練（屬 `stability-dev-verify`）；不動業務 topic；不重啟 connect、不重新註冊 connector
- **驗收測試**：無
- **驗收條件**：
  - [ ] 三個 topic 每個 partition 的 `Replicas`、`Isr` 都是 2 個，`min.insync.replicas=1`
  - [ ] `--under-replicated-partitions` 沒有輸出
  - [ ] connector 與 task 仍為 RUNNING
  - [ ] 回報附步驟 6 的輸出、回復檔位置；含密碼的備份已刪除
- **驗證指令**：`docker compose -f infra/docker-compose.yaml --env-file .env exec kafka_1 /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:29092 --describe --topic connect_configs`（三個 topic 各一次）；`curl -s localhost:8083/connectors/radar-cdc/status`
- **回報檔**：`.agent/reports/connect-rf-reassign.json`

## 執行資訊（ae task 產生）

- Issue：#306
- 分支：`chore/connect-rf-reassign`（從 develop 開出）
- 工作目錄：`.worktrees/connect-rf-reassign`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
