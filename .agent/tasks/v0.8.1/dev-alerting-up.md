# 派工單 dev-alerting-up

- **類型**：chore
- **負責**：backend
- **目標**：開發環境把熱度偵測 heat 與 Telegram bot 重新啟動起來，並刪掉遺留的 consumer group `uat-read-1793349393`。不改程式
- **背景**：2026-11-04 manager 看 `docker compose -p radar ps`，compose 裡沒有 heat、bot 容器，開發環境不會算熱度也不會推警示；甲方要恢復，因為 v0.8.1 驗收清單（`docs/uat/v0.8.1.md`）的「我的訂閱」與「允許清單」要靠 bot 實測。`uat-read-1793349393` 是 uat 重測讀 `replay.alerts` 留下的 group，甲方同意清掉（D-038 同性質）。主機上另有 uat 留下的回放 heat（PID 74977，group `heat-replay-1793345392`）由甲方自己 kill，不要動它。
- **設計依據**：Makefile `up-alerting`（compose profile `app`＋`alerting`）；開發規格 S5、7.20；D-010（bot 允許清單）；D-038
- **相依**：無
- **負責檔案**：
  - `.agent/reports/dev-alerting-up.json`
- **禁區**：不改程式、設定、`.env`（不可讀 `.env`）；不 `down`、不刪 volume；除了 heat、bot 以外不重建其他服務；只刪 `uat-read-1793349393` 這一個 group
- **驗收測試**：無
- **驗收條件**：
  - [ ] 先查 heat、bot 為什麼沒在跑（`docker compose -p radar ps -a` 是否有已結束的容器、最後的 log），寫進回報
  - [ ] 用 `docker compose -f infra/docker-compose.yaml --env-file .env --profile app --profile alerting up -d --wait heat bot` 啟動；兩個容器 Up，log 沒有 ERROR／traceback；heat log 有開始消費 `cdc.public.comments`，bot log 有開始輪詢
  - [ ] heat 的 consumer group lag 在下降或接近 0（附 `kafka-consumer-groups.sh --describe`）
  - [ ] 刪掉 `uat-read-1793349393` 前確認沒有成員，刪後 `--list` 沒有它，其他 group 不變；被自動模式擋下時停下，在回報寫出甲方要跑的指令
- **驗證指令**：回報附上實際執行的指令與輸出
- **回報檔**：`.agent/reports/dev-alerting-up.json`

## 執行資訊（ae task 產生）

- Issue：#285
- 分支：`chore/dev-alerting-up`（從 develop 開出）
- 工作目錄：`.worktrees/dev-alerting-up`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
