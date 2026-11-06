# 派工單 subscription-toggle-latency

- **類型**：fix
- **負責**：backend
- **目標**：「📋 我的訂閱」切換看板時，按鈕畫面在 2 秒內更新（#82）
- **背景**：甲方 v0.6.0 驗收回饋：點看板切換 ✅／⬜ 時有明顯延遲。開發規格階段 6 要求按鈕 2 秒內更新。延遲可能來自 answerCallbackQuery 的時機、PG 寫入、重查訂閱清單或 editMessageText，原因還沒查。要先量測，找出原因再修。開發規格要改的地方寫在回報的 open_questions。
- **設計依據**：#82；開發規格階段 6 驗收（按鈕 2 秒內）、7.21
- **相依**：無
- **負責檔案**：
  - `src/radar/bot/main.py`（只限 `on_callback`、`handle_update` 的 callback 流程）
  - `src/radar/bot/callbacks.py`（只限 `_subscriptions`、`_toggle_subscription`）
  - `src/radar/bot/repository.py`（只限訂閱查詢與切換）
  - `tests/unit/bot/test_main.py`
  - `tests/unit/bot/test_callbacks.py`
  - `tests/unit/bot/test_repository.py`
- **禁區**：不改訂閱資料表結構與 migration；不改推送、允許清單、指令迴圈的錯誤處理；不改畫面文案；不改開發規格
- **驗收測試**：
  - `tests/unit/acceptance/subscription-toggle-latency/`
- **驗收條件**：
  - [ ] 回報附上量測結果：各步驟（answerCallbackQuery、PG、重查、editMessageText）的耗時、主要延遲來源，以及量測方法
  - [ ] 點切換時先 answerCallbackQuery，再做比較慢的步驟；一次切換的 PG 查詢次數不比現在多
  - [ ] 切換後畫面的 ✅／⬜ 跟資料庫一致；連點兩次會回到原狀態
  - [ ] 驗收測試與 `make check` 通過；`grep -rn "TODO(subscription-toggle-latency)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/subscription-toggle-latency tests/unit/bot`；`make check`
- **回報檔**：`reports/subscription-toggle-latency.json`

## 執行資訊（task.py 產生）

- Issue：#248
- 分支：`fix/subscription-toggle-latency`（從 develop 開出）
- 工作目錄：`.worktrees/subscription-toggle-latency`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

### reports/subscription-toggle-latency.review.md

REQUEST_CHANGES 44d0065

# Review：subscription-toggle-latency（PR #250）

對照：`tasks/subscription-toggle-latency.md`、`reports/subscription-toggle-latency.json`、`reports/subscription-toggle-latency.qa.md`；`git diff develop...44d0065`（fbcbe17 驗收測試、44d0065 實作）。

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改 `bot/main.py`（`on_callback`、`handle_update` callback 段）、`bot/callbacks.py`（`_toggle_subscription`，另加 `handle_callback` 選填參數 `answer`、`CallbackResult.answered`，都是為了把 answer 傳進切換流程，可接受）、`tests/unit/bot/test_{main,callbacks}.py`；驗收測試目錄只有 qa 的 `test(...)` commit 動過 |
| 禁區 | 沒動 migration、資料表、推送、允許清單、文案、開發規格 |
| 寫死設定值 | 沒有 |
| 呼叫順序 | 先寫入（`subscribe`／`unsubscribe` 內含 commit）→ answer → 重查 `boards_of` → editMessageText；驗收測試 `test_toggle_answers_before_edit_and_before_requery` 也要求這個順序 |
| PG 查詢次數 | 重畫沿用 `enabled`，少一次 `enabled_boards`；`test_toggle_sql_count_not_more_than_baseline` 守住 |
| ✅／⬜ 與 DB 一致、連點兩次 | 寫入後重查 `boards_of`，驗收測試覆蓋 subscribe／unsubscribe／連點／不同看板／停用看板 |
| 例外處理 | `on_callback` 移進 try：PG 暫時性錯誤不被 Telegram 的 except 攔，照舊往上丟給 `poll_commands`；BadRequest／Forbidden 的處理沒變 |
| answer 在 session 內呼叫 | 寫入已 commit，answer 時沒有進行中的 transaction（下一句 SELECT 才開新的），不違反「transaction 裡不呼叫外部服務」 |

## qa 的兩點觀察

1. 重畫用切換前的 `enabled` 快照：同一請求內的毫秒級差距，下次操作就修正；換來少一次查詢。不算問題。
2. answer 排在寫入之後：toast 要反映寫入結果，寫入失敗時不會先顯示「已訂閱」；驗收測試也照這個順序寫。不算問題，但跟下面第 2 條有關：寫入是否是慢步驟沒有實測。

## 要修的問題

1. `tests/unit/bot/test_main.py:240` — `test_handle_update_answer_bad_request_inside_callback_is_skipped` 沒測到它名字講的路徑：`button(1)` 的 data 是 `1:menu:`（不是 SUB，answer 不會在 `on_callback` 裡呼叫），而 `FakeTelegram.answer_callback_query`（同檔約 94 行）從不丟 `error`，錯誤其實是 `edit_message_text` 丟的，跟既有的 `test_handle_update_edit_bad_request_is_skipped` 是同一個情境。回報與 qa 說「answer 在寫入後拋 BadRequest 有新增測試」不成立。— 要怎麼改：讓 FakeTelegram 可以只在 answer 時丟錯（例：加 `answer_error` 參數），用 SUB 的 callback data（`encode_callback(Action.SUB, ...)`）跑 `handle_update`，斷言 `edited == []`、不往外丟例外；再補一個 answer 丟 `TelegramForbiddenError` 時會走 `forget_blocked_chat` 的測試。這是本 PR 新增的錯誤路徑（answer 從 try 外的 `on_callback` 之後，變成在 `on_callback` 裡面）。
2. 驗收條件 1（量測）沒達成，修正對不上目標 — `reports/subscription-toggle-latency.json` open_questions[0..1] 只量了 SQLite 記憶體庫（三步合計約 4ms），answerCallbackQuery、editMessageText、PG 往返都沒量，「主要延遲來源」是推論。照這組數字，這次改動讓 answer 提早的只有一次 `boards_of` 加一次 `enabled_boards` 的時間（毫秒級），解釋不了甲方回饋的「明顯延遲」，也就無法證明 #82 的 2 秒內已達成。— 要怎麼改：在開發環境實測各步驟（例：在 `handle_update` 的 callback 流程用 `time.perf_counter` 記各步驟耗時並以 `log.debug` 輸出，對真實 PG 與 Telegram 按幾次切換取數字），把數字與真正的主要來源寫進回報；若實測後主要來源不在這四步（例如 getUpdates 迴圈本身），回報給 manager 另開單。若 manager 決定接受「無法在 sandbox 實測」，這條改為發版前在開發環境驗證的待辦，第 1 條仍要修。

## 附註（不擋合併，既有行為）

- `poll_commands` 遇到 PG 暫時性錯誤時 offset 不前進、整筆重做：若錯誤發生在寫入之後的 `boards_of`，重做會再切換一次（develop 上的 `_subscriptions` 重查也一樣）。不是這張單引入的，供 manager 決定是否開 issue。

問題數量：2

manager 對 review 第 2 項的處理：sandbox 連不到 Telegram，所以分兩部分做。
- PG：用整合測試 compose（`docker compose --env-file .env -f .worktrees/subscription-toggle-latency/compose.yaml run --rm test` 那組容器）在真實 PG 上量一次切換的 SQL 耗時，做完 `down -v`。
- Telegram：在 callback 流程加上各步驟耗時的 log，用 DEBUG 或 INFO 等級。內容只寫步驟名稱和毫秒，不寫 chat id 以外的個資。部署後由 manager 從開發環境 bot 的 log 取實測值，發版前甲方也會親手點點看。
回報裡要寫清楚哪些是實測、哪些是推論。第 1 項照 review 補上測試：在 SUB 回呼的流程內 answer 時丟出 BadRequest 或 Forbidden 的情況。
