# 派工單 bot-forbidden-crash

- **類型**：fix
- **負責**：backend
- **目標**：指令與按鈕路徑遇到 Telegram 403 時 bot 不再結束，也不會因同一筆 update 反覆重啟（資安 H-1）
- **背景**：v0.6.0 資安審查 FAIL 的唯一 high。`_send_reply` 與按鈕回呼只攔 `TelegramBadRequestError`，403 拋 `TelegramForbiddenError` → 指令 thread 結束 → alerts consumer 停 → 服務結束；offset 只在記憶體，重啟後同一筆 update 再觸發。alerts 推送路徑的 403 已照 7.21 處理，指令與按鈕路徑沒有
- **設計依據**：`docs/security/v0.6.0.md` H-1；`docs/development-spec.md` 7.21（403 = 使用者封鎖 bot，刪掉該 chat 的訂閱）
- **相依**：無
- **負責檔案**：
  - `src/radar/bot/main.py`
  - `src/radar/bot/telegram.py`
  - `tests/unit/bot/test_main.py`
  - `tests/unit/bot/test_telegram.py`
  - `docs/development-spec.md`（只有 7.21 需要補寫指令／按鈕路徑時）
- **禁區**：不改 `chat_settings`、`muted_posts` 等 schema 與 migration；不改 alerts 推送路徑既有行為；允許清單的預設值（D-010 待決定）不在這張單
- **驗收測試**：
  - `tests/unit/bot/acceptance/`
- **驗收條件**：
  - [ ] 回覆指令、回應按鈕時遇到 403：bot 不結束、alerts consumer 繼續運作，該 update 被確認（不會重啟後再拿到）
  - [ ] 403 的 chat 依 7.21 處理（與推送路徑一致）
  - [ ] 重現資安報告的情境（send_message 一律 403、模擬重啟兩次）不再結束
  - [ ] 新增與修改的函式都有單元測試
- **驗證指令**：`make check`
- **回報檔**：`reports/bot-forbidden-crash.json`

## 執行資訊（task.py 產生）

- Issue：#73
- 分支：`fix/bot-forbidden-crash`（從 develop 開出）
- 工作目錄：`.worktrees/bot-forbidden-crash`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
