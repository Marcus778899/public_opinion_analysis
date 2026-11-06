# 派工單 heat-alert-dup-investigate

- **類型**：chore
- **負責**：backend
- **目標**：只調查：找出同一個 `alert_id` 在 `replay.alerts` 出現兩筆的原因，以及 Quix `on_consumer_error` 回呼丟例外時 `app.run()` 會不會中止（#271）；不改程式，PR 作廢
- **背景**：
  - UAT v0.8.1 F-9 第 2 輪（`docs/uat/v0.8.1.md`）：同一 `alert_id` 先 `value` 62 後 143 兩筆
  - 程式邏輯上不該發生：`advance` 只結算 watermark 之後、`evaluate` 冷卻擋同一分鐘；重複代表 state 被回退或有兩份；bot 以 `alert_id` 去重，影響只在 `replay.alerts`／`alerts` 列數
  - 用整合測試環境（真的 Kafka、exactly-once）照第 2 輪資料重現；程式只放 scratchpad，不 commit
- **設計依據**：`docs/development-spec.md` 7.30 F（#271 重複 `alert_id`）與「需調查」2、3、派工順序第 4 列；7.20；D-042
- **相依**：無
- **負責檔案**：
  - 無（只在 scratchpad 與 compose `test` 服務重現）
- **禁區**：不改 repo 任何檔案、不 commit；不碰開發環境（專案 `radar`）的容器與 topic
- **驗收測試**：無
- **驗收條件**：
  - [ ] 回報寫明：是否重現、重現步驟與指令、根因（或排除了哪些假設）、建議修法與影響
  - [ ] 回報寫明需調查 3 的結論（有實際執行的證據）
  - [ ] 用完 `down -v` 釋放容器
- **驗證指令**：`docker compose --env-file .env -f .worktrees/heat-alert-dup-investigate/compose.yaml run --rm test pytest <scratchpad 測試路徑> -q -p no:xdist`，做完 `down -v`
- **回報檔**：`.agent/reports/heat-alert-dup-investigate.json`

## 執行資訊（ae task 產生）

- Issue：#305
- 分支：`chore/heat-alert-dup-investigate`（從 develop 開出）
- 工作目錄：`.worktrees/heat-alert-dup-investigate`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
