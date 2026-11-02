# 派工單 bot-skip-alert-log

- **類型**：fix
- **負責**：backend
- **通道**：fast
- **目標**：bot 因 chat_settings（通知設定）略過警示時記一行 log，說明 chat、unit、原因
- **背景**：UAT v0.6.0 F-7（docs/uat/v0.6.0.md、#81）：警示被通知設定擋掉時沒有任何紀錄，只能從沒有 sent 行推論
- **設計依據**：`docs/realtime-sentiment-radar-design.md` bot 通知設定相關章節；CLAUDE.md 的 log 規範
- **相依**：無
- **負責檔案**：
  - `src/radar/bot/notify.py`
  - `tests/unit/bot/test_notify.py`
- **禁區**：不改通知行為本身（哪些警示送、哪些略過）；不改 `src/radar/bot/` 其他檔；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 被通知設定略過時有一行 log（用 `radar.common.log`，等級 INFO 或 DEBUG，含 chat、unit、原因）；正常送出的行為與 log 不變
  - [ ] 單元測試涵蓋：被略過有 log、沒被略過時沒有這行 log
  - [ ] `make check` 通過；PR 的 CI 全綠
- **驗證指令**：`make check`
- **回報檔**：`reports/bot-skip-alert-log.json`

## 執行資訊（task.py 產生）

- Issue：#130
- 分支：`fix/bot-skip-alert-log`（從 develop 開出）
- 工作目錄：`.worktrees/bot-skip-alert-log`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-21

### 範圍調整（回應 worker 回報的 blocked，採 A）

- 負責檔案追加：`src/radar/bot/repository.py`、`src/radar/bot/main.py`，以及對應的 `tests/unit/bot/test_repository.py`（若存在則沿用）、`tests/unit/bot/test_main.py`
- 可以讓 `recipients` 回傳或記下被略過的 chat 與原因；做法由你決定，但要維持一次查詢內完成、不額外對每個 chat 查 PG
- 禁區不變：送給誰、略過誰的結果必須跟現在完全一樣（測試要能證明）；不改 schema、不寫 PG
- 改動超過 fast 條件會自動升級 full，沒關係，不要為了留在 fast 而縮減

## 追加 2026-10-21

### 負責檔案更新（manager，取代原欄位；依上一則追加的 A 方案）

- **負責檔案**：
  - `src/radar/bot/notify.py`
  - `src/radar/bot/repository.py`
  - `src/radar/bot/main.py`
  - `tests/unit/bot/test_notify.py`
  - `tests/unit/bot/test_repository.py`
  - `tests/unit/bot/test_main.py`
