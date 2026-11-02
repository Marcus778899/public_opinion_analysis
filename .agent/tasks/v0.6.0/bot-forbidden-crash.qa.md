PASS 9af39cb

# bot-forbidden-crash 驗證證據

驗證對象：`.worktrees/bot-forbidden-crash` HEAD 9af39cb（PR #75）。

## 環境
worktree 的 `.env` symlink 會讓 pytest 在 sandbox 收集階段 PermissionError，所以用 `git archive HEAD` 解到 scratchpad（只含追蹤檔、無 `.env`），以主目錄 `.venv` 的 pytest／ruff 執行，`PYTHONPATH=src`（已確認 `radar.bot.main` 載入的是副本的 src）。

## 指令與輸出
- `ruff check .` -> `All checks passed!`
- `ruff format --check .` -> `228 files already formatted`
- `pytest tests/unit -q`（全部）-> `1009 passed in 4.93s`（worker 回報的 11 個 bot 以外失敗是它的副本缺檔，完整追蹤檔下不存在）
- `pytest tests/unit/bot/acceptance -q` -> `14 passed`
- 對照：同一份 acceptance 放到 develop 的程式上 -> `13 failed, 1 passed`，確認測試真的會抓到 H-1。
- `grep -rn "TODO(bot-forbidden-crash)" src tests` -> 無結果

## 驗收條件
1. 回覆指令／回應按鈕 403：`_send_reply`、按鈕回呼（answer_callback_query 與 edit_message_text 同一個 try）都新增攔 `TelegramForbiddenError`；`poll_commands` 在 handle_update 後照常 `offset = update_id + 1`（`test_poll_commands_forbidden_reply_advances_offset` 驗 offsets `[None, 2]`）。通過。
2. 403 依 7.21：呼叫 `PreferenceRepository.forget`（刪 Subscription、ChatSettings、MutedPost），與 notify.py 推送路徑相同；acceptance 驗證不影響其他 chat。通過。
3. H-1 情境：`test_h1_repro_always_forbidden_two_restarts_never_die` 與 `..._for_any_chat`（send_message 一律 403、兩次重啟）通過，develop 上同測試失敗。通過。
4. 新增函式 `forget_blocked_chat` 與兩條新分支都有單元測試（test_main.py 4 項）。通過。

## 其他檢查
- 程式只動 `main.py` 與 7.21 一行文件；未動 schema／migration／notify.py；無寫死設定值。
- `telegram.get_updates`／`set_my_commands` 的 403 不在 H-1 範圍（get_updates 的 403 非使用者封鎖情境）。

## 限制（不影響判定）
- 環境沒有 mypy、bandit（pre-commit 的 bandit hook 未能跑）；新增程式碼無 subprocess／eval 等 bandit 關注項。
- 未跑 pre-commit 本體，改以其包含的 ruff、ruff-format 直接執行。
