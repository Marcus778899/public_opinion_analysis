# 派工單 bot-poll-resilience

- **類型**：fix
- **負責**：backend
- **目標**：bot 指令迴圈在 PG 斷線、Telegram 網路錯誤時穩定重試，不會整個重啟，也不會讓按鈕長時間沒反應（#79、#67）
- **背景**：#79 來自資安 v0.6.0 L-4：`poll_commands` 的 `purge_muted` 在 try 外面連 PG，PG 斷線時整個迴圈會重啟。#67 來自 UAT v0.6.0 F-4：長輪詢遇到 ReadTimeout／ConnectError 時會連續 WARNING 約 20 分鐘才恢復。開發規格目前由 scheduler-statement-timeout 單在改；需要改開發規格時，寫在回報的 open_questions，之後補。
- **設計依據**：#79、#67；docs/security/v0.6.0.md L-4；docs/uat/v0.6.0.md F-4；開發規格階段 6（bot）
- **相依**：無
- **負責檔案**：
  - `src/radar/bot/main.py`（只限 `poll_commands`、`purge_muted` 與它們的錯誤處理）
  - `src/radar/bot/telegram.py`（只限長輪詢的逾時與退避）
  - `tests/unit/bot/test_main.py`
  - `tests/unit/bot/test_telegram.py`
- **禁區**：不改允許清單與推送邏輯（`recipients`、`check_allowlist`）；不改訂閱資料；不改開發規格
- **驗收測試**：
  - `tests/unit/acceptance/bot-poll-resilience/`
- **驗收條件**：
  - [ ] PG 斷線算暫時性錯誤：記 WARNING 後重試，指令迴圈不中止；PG 恢復後照常處理
  - [ ] 單筆 update 出現其他意外例外：記錄後跳過，offset 照常前進，不會一直重複處理同一筆
  - [ ] Telegram ReadTimeout／ConnectError 的退避有上限，上限值寫在程式常數或設定；恢復後下一輪就能收到指令
  - [ ] 驗收測試與 `make check` 通過；`grep -rn "TODO(bot-poll-resilience)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/bot-poll-resilience tests/unit/bot`；`make check`
- **回報檔**：`reports/bot-poll-resilience.json`

## 執行資訊（task.py 產生）

- Issue：#236
- 分支：`fix/bot-poll-resilience`（從 develop 開出）
- 工作目錄：`.worktrees/bot-poll-resilience`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

### reports/bot-poll-resilience.review.md

REQUEST_CHANGES 079d55a

# Review：PR #242 bot-poll-resilience

依據：派工單 `tasks/bot-poll-resilience.md`（本單沒有 docs/contracts，以驗收條件當契約）、仲裁 `reports/bot-poll-resilience.ruling.md`、qa 證據 `reports/bot-poll-resilience.qa.md`。diff 來源：`git diff develop...079d55a`（與 `gh pr view 242` 的檔案清單一致）。

## 檢查項目

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改 `src/radar/bot/main.py`（import、常數、`poll_commands`）、`tests/unit/bot/test_main.py`；驗收測試只有 qa 的 `test(...)` commit（ee82d2e、079d55a，後者照仲裁改 fixture） |
| 禁區 | 沒碰 `recipients`、`check_allowlist`、訂閱資料、開發規格 |
| 寫死設定 | `POLL_BACKOFF_MAX_S = 30.0` 是程式常數，派工單允許「常數或設定」 |
| 驗收條件 1（PG 斷線） | purge 失敗只 WARNING、不更新 `last_purge`；handle_update 的 PG 錯誤往外拋到外層退避、offset 不前進。符合 |
| 驗收條件 2（單筆意外例外） | 記 WARNING、offset 前進。符合，但範圍過寬，見問題 1 |
| 驗收條件 3（退避上限） | `backoff_delays` 預設 `max_s` 本來就是 30，改成顯式常數；getUpdates 的 ReadTimeout／ConnectError 已在 `telegram.py:_call` 轉 TransientError。符合 |
| 安全 | log 只寫 `update_id` 與例外 repr；TransientError 訊息原本就去掉含 token 的網址 |
| 測試 | 單元測試 3 個新案例涵蓋 purge PG 斷線、意外例外跳過、handle_update PG 斷線；驗收測試 10 個 |

## 問題

1. `src/radar/bot/main.py:185` — `except Exception` 會吃掉回覆時的 `TransientError`（`send_message`、`answer_callback_query`、`edit_message_text` 遇到 429 或網路錯誤，`telegram.py:_call` 轉成 TransientError）。develop 的行為是往外拋到 `except TransientError`：照 `retry_after_s` 等待、offset 不前進、重做這筆；這個 PR 改成直接跳過這筆並前進 offset，使用者的指令或按鈕在 Telegram 短暫故障時被靜默丟掉，429 的 `retry_after` 也不再遵守。這和本單「網路錯誤時穩定重試、按鈕不會沒反應」的目標相反。已重現（不改 worktree，用 `PYTHONPATH` 在 scratchpad 跑 `tests/unit/bot/test_main.py` 的 `run([[msg(1)], [msg(1)]], error=TransientError("429", retry_after_s=3))`）：
   - develop：`offsets [None, None, None] waits [3, 3]`（等 3 秒、重做）
   - PR：`offsets [None, 2, 2] waits []`，log `update 1 skipped after unexpected error: TransientError('429')`

   要怎麼改：把 TransientError 和 PG 錯誤一樣排除在「意外例外」之外，例如 `except (TransientError, *_PG_TRANSIENT): raise`（放在 `except Exception` 前面）。
2. `tests/unit/bot/test_main.py`（新增區塊之後）— 缺少回歸測試：回覆時 `TransientError` 要等待 `retry_after_s`、offset 不前進、之後重做。要怎麼改：新增 `test_poll_commands_reply_transient_error_retries_same_update`，斷言 `telegram.offsets[:2] == [None, None]` 且 `waits[0] == 3`。按鈕路徑（`answer_callback_query`）也要涵蓋，或者至少拿參數化測試涵蓋 `edit_message_text`。

## 非阻擋備註

- handle_update 在部分完成後才遇到 PG 錯誤（例如已經 `answer_callback_query`、`forget_blocked_chat` 才斷線）時，重做會重送一次回覆；機率低、可以接受，不用改。
- 開發規格階段 6 要補「指令迴圈錯誤分類」：worker 已列進 open_questions，由 manager 之後補。

問題數量：2
