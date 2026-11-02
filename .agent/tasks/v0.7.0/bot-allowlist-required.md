# 派工單 bot-allowlist-required

- **類型**：fix
- **負責**：backend
- **目標**：Telegram bot 的允許清單改成 fail closed：`TELEGRAM_ALLOWED_CHAT_IDS` 沒設（或空）就啟動失敗，要開放所有人必須明確設 `TELEGRAM_ALLOW_ALL=true`（D-010）
- **背景**：資安 v0.6.0 M-1。現況空清單＝不限制（`src/radar/common/settings.py` 的 `TelegramSettings.allowed_chat_ids`、`src/radar/bot/main.py`）。既有測試 `tests/unit/common/test_settings.py` 的「空＝不限制」要改成新行為；`tests/unit/bot/acceptance/` 是前一張單鎖定的驗收測試，以 `allowed_chat_ids=[]` 建 settings，改完仍須通過（不可改它）。`TELEGRAM_ALLOW_ALL` 是選填，依 D-009 在 `.env.example` 寫成註解
- **設計依據**：D-010、D-009；設計文件 9.2；開發規格 7.21
- **相依**：無
- **負責檔案**：
  - `src/radar/common/settings.py`、`src/radar/bot/main.py`
  - `tests/unit/common/test_settings.py`、`tests/unit/bot/test_main.py`
  - `.env.example`
  - `docs/realtime-sentiment-radar-design.md`（9.2）、`docs/development-spec.md`（7.21）
- **禁區**：不改 `tests/unit/bot/acceptance/`；不改其他服務；不讀 `.env`
- **驗收測試**：
  - `tests/unit/acceptance/bot_allowlist/`
- **驗收條件**：
  - [ ] 清單沒設或空、且 `TELEGRAM_ALLOW_ALL` 不是 true：bot 啟動失敗，log 說明要設哪個變數
  - [ ] 清單有值：只回應清單內 chat（含按鈕回呼）；`TELEGRAM_ALLOW_ALL=true`：回應所有 chat，啟動 log 明確警告
  - [ ] 清單有值又設 `TELEGRAM_ALLOW_ALL=true` 時的行為有定義並寫進 7.21
  - [ ] `make check` 通過；`grep -rn "TODO(bot-allowlist-required)" src tests` 無結果
- **驗證指令**：`make check`
- **回報檔**：`reports/bot-allowlist-required.json`

## 執行資訊（task.py 產生）

- Issue：#91
- 分支：`fix/bot-allowlist-required`（從 develop 開出）
- 工作目錄：`.worktrees/bot-allowlist-required`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
