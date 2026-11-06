APPROVE d82b7e2

# Review（第 2 輪）：subscription-toggle-latency（PR #250）

對照：`tasks/subscription-toggle-latency.md`（含 2026-10-29 追加與 manager 的處理方式）、`reports/subscription-toggle-latency.json`、`reports/subscription-toggle-latency.qa.md`；`git diff develop...d82b7e2`（fbcbe17 驗收測試、44d0065 實作、d82b7e2 耗時 log 與補測試）。

## 實際執行

- `PYTHONPATH=<worktree>/src uv run pytest tests/unit/acceptance/subscription-toggle-latency tests/unit/bot` → 211 passed
- `grep -rn "TODO(subscription-toggle-latency)" src tests` → 無結果
- `uv run ruff check src tests` → All checks passed
- `git log develop..HEAD -- tests/unit/acceptance` → 只有 qa 的 fbcbe17

## 上一輪的 2 項

| 項目 | 結果 |
|---|---|
| 1. SUB 回呼 answer 遇 BadRequest／Forbidden 沒有測試 | 已修。`tests/unit/bot/test_main.py` 的 `_sub_press` 用 SUB data（`1:sub:Stock`）跑 `handle_update`，`AnswerFails` 只在 answer 時丟錯；BadRequest 斷言 `edited == []`，Forbidden 斷言 `forgotten == [8]`。名稱不符的舊測試已移除 |
| 2. 只在 SQLite 量 | 照 manager 的處理：PG 在整合 compose 實測（各步中位 0.66～1.9ms，合計約 5ms，已 down -v），Telegram 加了逐步耗時 log 待部署後取值；回報分成【實測】、【未實測】、【推論】三段。驗收條件 1 的 Telegram 部分改成發版前的待辦（見下方「給 manager」） |

## 這一輪檢查了什麼

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改 `bot/main.py`（`on_callback`、`handle_update` 的 callback 段）、`bot/callbacks.py`（`_toggle_subscription`；另加 `timed` helper、`handle_callback` 選填參數 `answer`、`CallbackResult.answered`，都是為了量測和把 answer 傳進切換流程，可以接受）、`tests/unit/bot/test_{main,callbacks}.py`。`repository.py` 沒動 |
| 禁區 | 沒動 migration、資料表、推送、允許清單、指令迴圈的錯誤處理（`poll_commands` 沒改）、文案、開發規格 |
| 寫死設定值 | 沒有 |
| 耗時 log | `timed` 以 `log.info("callback step=%s chat=%s ms=%.1f")` 輸出，只帶步驟名、chat id、毫秒，符合 manager 的指示；放在 `finally`，例外照常往外丟（`test_timed_logs_even_when_step_raises`）。6 個步驟都有 log（`test_sub_toggle_logs_every_step` 驗證順序） |
| answer 在 `handle_callback` 裡丟錯會不會被吞掉 | 不會。`handle_callback` 只攔 `QUERY_ERRORS = (ClickHouseError, httpx2.TransportError)`（`stats.py:15`）；Telegram client 會把 `httpx2.TransportError` 轉成 `TransientError`（`telegram.py:138-140`），BadRequest／Forbidden 也都直接繼承 `Exception`，所以全部會穿過 `on_callback` 的 `with sessions()`，交給 `handle_update` 的 except 處理。因此用 monkeypatch 換掉 `on_callback` 的測試，跟實際路徑等價 |
| transaction 與外部呼叫 | 寫入在 answer 之前就 commit 了；answer 丟錯時離開 session，不會留下沒 commit 的寫入 |
| 呼叫順序、SQL 次數、畫面與 DB 一致、連點兩次 | 驗收測試全部通過；重畫沿用 `enabled`，查詢次數比 develop 少一次 |
| 非 SUB 的 action、找不到看板 | `answered=False`，由 `handle_update` 照舊 answer（`test_sub_toggle_unknown_board_does_not_call_answer`、`test_sub_toggle_without_answer_hook_leaves_answered_false`） |

## 非阻擋觀察

- qa 觀察 1（main 層沒有不 monkeypatch 的端到端測試）：上表已經用程式碼確認例外路徑等價，不要求補。
- `callback.chat_id or 0`：`is_allowed` 已經擋掉 `None`，實際上不會走到 0。
- 每個按鈕都會多 1～6 行 INFO log。量完 #82 之後，manager 可以決定要不要降成 DEBUG。

## 給 manager

- 驗收條件 1 的 Telegram 往返（answerCallbackQuery、editMessageText）還沒實測。#82 的「2 秒內」要等部署後從 bot log 的 `callback step=` 取數字才能確認；依回報的推論，主要延遲來源可能不在這四步（例如 getUpdates 迴圈），到時可能要另開單。
- 開發規格要同步的地方（階段 6、7.21／7.23 的 answer 時機與耗時 log 格式）列在回報 open_questions，worker 因為禁區不能改。
- 上一輪附註仍然有效（既有行為）：`poll_commands` 遇到 PG 暫時性錯誤或 Telegram `TransientError` 時 offset 不前進；如果錯誤發生在寫入之後，重做會再切換一次。

問題數量：0
