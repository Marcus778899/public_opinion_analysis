APPROVE 9af39cb

# PR #75 bot-forbidden-crash code review

對照：`tasks/bot-forbidden-crash.md`、`docs/security/v0.6.0.md` H-1、`docs/development-spec.md` 7.21／7.23（第 991 行）、`src/radar/bot/notify.py` 推送路徑。

## 檢查項目

| 項目 | 結果 |
|---|---|
| 負責檔案 | worker commit 9af39cb 只改 `src/radar/bot/main.py`、`tests/unit/bot/test_main.py`、`docs/development-spec.md`；`tests/unit/bot/acceptance/` 是 qa 的 commit 3a50cce。沒動 schema、migration、`notify.py`、允許清單 |
| H-1 修法 | `_send_reply`（`main.py:188-196`）和按鈕回呼（`main.py:117-128`，answer 與 edit 在同一個 try）都多攔了 `TelegramForbiddenError`，例外不會再往上丟出 `handle_update`，`poll_commands` 照常執行 `offset = update_id + 1`（`main.py:170-172`），所以 update 會被確認，重啟後不會再送一次 |
| 與推送路徑一致（7.21） | 新的 `forget_blocked_chat` 跟推送路徑 `main()` 裡的 `forget_chat` 一樣呼叫 `PreferenceRepository.forget`（`repository.py:137`，刪 Subscription／ChatSettings／MutedPost 後 commit），log 文字也相同。這跟 7.21 和第 991 行的規定一致 |
| 會不會誤刪 | 只有 `TelegramForbiddenError` 會刪資料，`raise_for_response` 只在 HTTP 403 時拋這個例外（`telegram.py:164`）。400、429、5xx、連線錯誤走原本的分支，沒有變。刪除的 chat_id 來自 Telegram 自己的 update（`message.chat_id`／`callback.chat_id`），不是使用者輸入的值，所以不能拿來刪別人的資料。驗收測試 `test_poll_forbidden_does_not_touch_other_chats` 和 `test_handle_update_non_forbidden_chat_keeps_subscription` 有涵蓋這點 |
| 403 的語意 | 在指令／按鈕路徑上，403 代表使用者封鎖 bot、bot 被踢出群組或帳號停用，chat 都已經收不到訊息。刪除訂閱跟推送路徑的做法一致，沒有引入新的資料問題 |
| 文件 7.21（`development-spec.md:932`） | 補上「推送、指令回覆、按鈕回應三條路徑都一樣處理；處理完該 update 照常確認」，跟實作相符。第 991 行（同時刪 chat_settings、muted_posts）不必改 |
| 設定值／安全 | 沒有寫死的值。log 只記 chat_id，沒有 token |
| 測試 | 單元測試 4 項涵蓋 `forget_blocked_chat`、回覆 403、按鈕 403、offset 前進 `[None, 2]`。驗收測試 14 項涵蓋三個驗收條件，包含 H-1 重啟兩次的重現。qa 證據顯示這些驗收測試在 develop 上 13 項失敗，代表測試真的抓得到 H-1 |
| 實跑 | `git archive 9af39cb` 解到 scratchpad，執行 `PYTHONPATH=src .venv/bin/pytest -q tests/unit/bot`，結果 `177 passed in 0.63s` |

## 不擋合併的建議（可另開單）

- `main.py:239-241` 推送路徑的 `forget_chat` closure 跟 `forget_blocked_chat` 重複，可以改成 `functools.partial(forget_blocked_chat, sessions)`。這張單的禁區是「不改推送路徑既有行為」，所以這次不要求改
- `forget_blocked_chat` 本身寫 DB，PG 暫時斷線時拋出的 SQLAlchemy 例外仍然會讓指令 thread 結束。這不是這次改出來的問題：`reply_to`、`on_callback` 原本就會碰 DB，屬於既有的同類風險，不在 H-1 範圍內，建議交給 security 在 v0.6.0 複查時判斷要不要開單
- mypy、bandit 本機沒有跑，交給 CI
