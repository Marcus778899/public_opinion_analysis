APPROVE 2d66305

# Review（第 2 輪）：PR #242 bot-poll-resilience

依據：派工單 `tasks/bot-poll-resilience.md`（含檔尾上一輪 review 追加；本單沒有 docs/contracts，以驗收條件當契約）、qa 證據 `reports/bot-poll-resilience.qa.md`（PASS 2d66305）。diff 來源：`git diff develop...2d66305`，與 `gh pr view 242` 的檔案清單一致（`src/radar/bot/main.py`、`tests/unit/bot/test_main.py`、驗收測試）。

## 上一輪問題

| # | 問題 | 結果 |
|---|---|---|
| 1 | `main.py` 的 `except Exception` 吃掉回覆時的 `TransientError` | 已修：`except (TransientError, *_PG_TRANSIENT): raise` 放在 `except Exception` 之前，TransientError 回到外層照 `retry_after_s` 等待、offset 不前進 |
| 2 | 缺回歸測試 | 已補：`test_poll_commands_reply_transient_error_retries_same_update` 參數化訊息（`send_message`）與按鈕（`edit_message_text`）兩條路徑，斷言 `offsets[:2] == [None, None]`、`waits[0] == 3`；qa 的突變驗證（改回舊寫法時 2 failed）確認測試抓得到這個問題 |

## 完整 diff 檢查

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改 `main.py` 的 import、常數、`poll_commands`，以及 `tests/unit/bot/test_main.py`；驗收測試目錄只有 qa 的 `test(...)` commit（ee82d2e、079d55a） |
| 禁區 | 沒碰 `recipients`、`check_allowlist`、訂閱資料、開發規格 |
| 寫死設定 | 只有程式常數 `POLL_BACKOFF_MAX_S = 30.0`（派工單允許常數） |
| 驗收條件 1（PG 斷線） | `purge_muted` 失敗只 WARNING、不更新 `last_purge`；`handle_update` 的 `OperationalError`／`InterfaceError` 往外拋到 `except _PG_TRANSIENT` 退避，offset 不前進。符合 |
| 驗收條件 2（單筆意外例外） | 其他例外記 WARNING、offset 前進；TransientError 與 PG 錯誤已排除。符合 |
| 驗收條件 3（退避上限） | 兩處 `backoff_delays(max_s=POLL_BACKOFF_MAX_S)`；getUpdates 的 ReadTimeout／ConnectError 由 `telegram.py:_call` 轉 TransientError。符合 |
| 既有錯誤路徑 | `TelegramBadRequestError`、`TelegramForbiddenError` 在 `handle_update`／`_send_reply` 內處理，行為不變（`test_poll_commands_forbidden_reply_advances_offset` 通過） |
| 安全 | log 只寫 `update_id` 與例外 repr；TransientError 訊息不含 token 網址 |
| 驗收條件 4 | 已實跑，見下 |

## 實際執行（worktree，HEAD 2d66305）

```
uv run pytest tests/unit/acceptance/bot-poll-resilience tests/unit/bot -q  -> 200 passed in 0.47s
uv run ruff check src tests/unit/bot                                       -> All checks passed!
grep -rn "TODO(bot-poll-resilience)" src tests                             -> 無結果
```

## 非阻擋備註（沿用上一輪）

- `handle_update` 部分完成後才遇到 PG 或 Telegram 暫時性錯誤時，重做會重送一次回覆；機率低、可接受。
- 開發規格階段 6 要補「指令迴圈錯誤分類」，worker 已列 open_questions，由 manager 之後補。

問題數量：0
