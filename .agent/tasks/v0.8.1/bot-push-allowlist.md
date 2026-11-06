# 派工單 bot-push-allowlist

- **類型**：fix
- **負責**：backend
- **目標**：警示推送也照允許清單過濾：不在 `TELEGRAM_ALLOWED_CHAT_IDS` 的 chat 不再收到推送，不刪任何訂閱資料（#121）
- **背景**：資安 v0.7.0 L-6。v0.6.0 fail open 期間有陌生 chat 訂閱；之後設了允許清單，這些 chat 的指令會被擋，但推送照樣會收到。這次只在推送時過濾，不刪資料：刪資料屬於決策分級④，不做。`TELEGRAM_ALLOW_ALL=true` 時照舊推給所有訂閱者（D-010）。開發規格目前由 spec-docs-sync 在改，需要動文件的地方寫進回報的 open_questions。
- **設計依據**：#121；docs/security/v0.7.0.md L-6；D-010；`src/radar/bot/main.py` 的 `is_allowed`、`recipients`
- **相依**：無
- **負責檔案**：
  - `src/radar/bot/main.py`（只限 `main()` 裡推送收件人的過濾）
  - `tests/unit/bot/test_main.py`
- **禁區**：不刪或改 PG 的訂閱資料；不改 `is_allowed`、`check_allowlist` 的現有規則、指令處理與 callback；不改開發規格
- **驗收測試**：
  - `tests/unit/acceptance/bot-push-allowlist/`
- **驗收條件**：
  - [ ] 有設允許清單時，推送只送給清單內的訂閱 chat；不在清單的 chat 不送，訂閱資料不變
  - [ ] `TELEGRAM_ALLOW_ALL=true` 時照舊送給所有訂閱者
  - [ ] 被過濾掉的收件人數記 INFO 或 DEBUG（不記 chat id 以外的個資）
  - [ ] 驗收測試與 `make check` 通過；`grep -rn "TODO(bot-push-allowlist)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/bot-push-allowlist tests/unit/bot`；`make check`
- **回報檔**：`reports/bot-push-allowlist.json`

## 執行資訊（task.py 產生）

- Issue：#244
- 分支：`fix/bot-push-allowlist`（從 develop 開出）
- 工作目錄：`.worktrees/bot-push-allowlist`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
