PASS d82b7e2

# QA：subscription-toggle-latency（PR #250，d82b7e2）

## 指令與結果（PYTHONPATH=worktree/src，已確認 radar.bot.callbacks 載入 worktree 檔且有 timed）
- `uv run pytest tests/unit/acceptance/subscription-toggle-latency tests/unit/bot` → 211 passed
- 等同 make check：`pre-commit run --all-files`（trailing whitespace、eof、yaml、ruff、ruff format、bandit 全 Passed）；`uv run pytest tests/unit` → 1737 passed in 75.34s；`ruff check .` All checks passed；`ruff format --check .` 319 files already formatted
- `grep -rn "TODO(subscription-toggle-latency)" src tests` → 無結果
- `git diff --stat fbcbe17 HEAD -- tests/unit/acceptance` → 空，驗收測試自 qa 的 test commit 後未動

## 驗收條件
1. 量測結果：回報 open_questions 分【實測】（真實 PG 各步驟中位 0.66～1.9ms，合計約 5ms，30 次，fsync=off、無網路）、【未實測】（Telegram 往返，已加 log，待部署後取值）、【推論】（來源很可能在 Telegram 或 getUpdates，不在 PG）。依 manager 對 review 第 2 項的處理方式，符合。PG 數字為 worker 自述的臨時整合測試（未提交），我未重跑，只能檢視其說明。
2. 先 answer 再做慢步驟、PG 查詢數不增：驗收測試通過（含 sql_count 與呼叫順序）。
3. ✅／⬜ 與 DB 一致、連點兩次還原：驗收測試通過。
4. 驗收測試與 check 通過、無 TODO：如上。

## 新增三項
- SUB 回呼 answer 丟錯測試：`test_handle_update_sub_answer_bad_request_skips_edit`（edited == []）、`test_handle_update_sub_answer_forbidden_forgets_chat`（forgotten == [8]）通過；FakeTelegram 子類只在 answer 丟錯，data 為 SUB 格式。
- 耗時 log：格式 `callback step=%s chat=%s ms=%.1f`、log.info。diff 中唯一新增的 log 呼叫就是這條，內容只有步驟名、chat id、毫秒，無其他個資。`timed` 以 try/finally，例外照常往外傳；`test_timed_logs_even_when_step_raises` 覆蓋。原流程順序（enabled_boards → boards_of → 寫入 → answer → 重查 → edit）與 except 區塊未變。
- 無改動驗收測試。

## 觀察（不構成 FAIL）
- 上述 answer 丟錯測試以 monkeypatch 取代 `on_callback`，在其中直接呼叫 answer，沒走真實的 `_toggle_subscription`；真實 answer 傳遞已由 callbacks 單元測試與驗收測試覆蓋，但 main 層端到端組合沒有單一測試。
- `callback.chat_id or 0`：chat_id 為 None 時 log 會寫 chat=0，無害。
- #82 的 2 秒目標尚未證實達成，需部署後從 log 取 Telegram 步驟耗時，再由 manager 判斷是否另開單（回報已寫明）。
