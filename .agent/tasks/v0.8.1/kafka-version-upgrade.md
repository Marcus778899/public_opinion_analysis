# 派工單 kafka-version-upgrade

- **類型**：chore
- **負責**：backend
- **目標**：依 D-034 把 `.env.example` 的 `KAFKA_VERSION` 改為 4.1.2，讓 CI 以新版跑全部整合測試（開發規格派工順序稱 `kafka-upgrade-4-1-2`，流程不允許數字段命名，改用此名）
- **背景**：10-28 管線停 10 小時是 Kafka 4.1.0 的 KAFKA-19888，4.1.2 已修（開發規格 7.28 C）。甲方已把 `.env` 改成 4.1.2；開發環境逐台升級由 manager 照 7.28 C 做（不在本單）
- **設計依據**：`docs/development-spec.md` 7.28 C 與派工順序第 3 列；D-034
- **相依**：`pipeline-stall-alert`（已合併）
- **負責檔案**：
  - `.env.example`
- **禁區**：不改 compose、其他設定；不碰 `.env`；不重啟開發環境的 kafka
- **驗收測試**：無
- **驗收條件**：
  - [ ] `.env.example` 的 `KAFKA_VERSION=4.1.2`，其他行不變
  - [ ] 整合測試以新版跑過：`docker compose --env-file .env -f .worktrees/kafka-version-upgrade/compose.yaml run --rm test`（`.env` 已是 4.1.2），跑完 `down -v`；並以 PR 的 CI 結果佐證
- **驗證指令**：見驗收條件；CI 全綠
- **回報檔**：`reports/kafka-version-upgrade.json`

## 執行資訊（task.py 產生）

- Issue：#228
- 分支：`chore/kafka-version-upgrade`（從 develop 開出）
- 工作目錄：`.worktrees/kafka-version-upgrade`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
