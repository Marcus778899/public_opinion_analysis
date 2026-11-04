PASS 2d66305

# QA：bot-poll-resilience（PR #242，HEAD 2d66305）

全部在 `.worktrees/bot-poll-resilience`、`PYTHONPATH=$PWD/src` 下實際執行。

## 驗收條件

| 條件 | 結果 | 依據 |
|---|---|---|
| PG 斷線：WARNING 後重試、迴圈不中止、恢復後照常 | 通過 | `purge_muted` 失敗只記 WARNING、不更新 `last_purge`；`handle_update` 的 `OperationalError`／`InterfaceError` 往外拋，由 `except _PG_TRANSIENT` 退避，offset 不前進。單元 `test_poll_commands_purge_pg_down_*`、`test_poll_commands_update_pg_down_keeps_offset_and_waits` 與驗收測試通過 |
| 單筆其他意外例外：記錄跳過、offset 前進 | 通過 | `except Exception` 記 WARNING 後 `offset = update_id + 1`；`test_poll_commands_unexpected_update_error_skips_and_advances_offset` 通過 |
| Telegram 退避有上限且寫成常數 | 通過 | `POLL_BACKOFF_MAX_S = 30.0`，兩處 `backoff_delays(max_s=...)`；驗收測試通過 |
| 驗收測試與 make check 通過；無 TODO | 通過 | 見下；`grep -rn "TODO(bot-poll-resilience)" src tests` 無結果 |

## 本輪 review 問題（回覆時 TransientError 被吞掉）

- 程式：`except (TransientError, *_PG_TRANSIENT): raise` 放在 `except Exception` 之前，TransientError 回到外層，照 `retry_after_s` 等待、offset 不前進。
- 回歸測試 `test_poll_commands_reply_transient_error_retries_same_update`（訊息、按鈕兩種）斷言 `offsets[:2] == [None, None]` 且 `waits[0] == 3`。
- 突變驗證（在 scratchpad 複本把該行改回 `except _PG_TRANSIENT:`）：兩個參數化案例都失敗（`2 failed, 42 passed`），log 出現 `update 1 skipped after unexpected error: TransientError('429')`，確認測試真能抓到此問題；正式程式碼通過。
- PG 暫時性錯誤與其他意外例外的行為未被改壞：相關測試全數通過（見下）。

## 執行輸出

```
uv run pytest tests/unit/acceptance/bot-poll-resilience -q   -> 10 passed in 0.31s
uv run pytest tests/unit/acceptance -q（整個目錄）           -> 409 passed in 71.16s
uv run pytest tests/unit/bot -q                              -> 190 passed in 0.41s
pre-commit run --all-files   -> 全部 Passed（trailing whitespace、eof、yaml、ruff、ruff format、bandit）
uv run ruff check .          -> All checks passed!
uv run ruff format --check . -> 314 files already formatted
uv run pytest tests/unit -q（make check 的測試部分）          -> 1667 passed in 73.61s
```

## 其他檢查

- 寫死設定：新增的只有程式常數 `POLL_BACKOFF_MAX_S`（派工單允許）；沒有 port、網址、token。
- 範圍：改動限於 `src/radar/bot/main.py`（import、常數、`poll_commands`）與 `tests/unit/bot/test_main.py`，加上驗收測試；沒碰 `recipients`、`check_allowlist`、開發規格。
- 邊界備註（非阻擋，與 review 一致）：`handle_update` 部分完成後才遇到 PG 斷線，重做時可能重送一次回覆，接受。
- 開發規格階段 6 待補「指令迴圈錯誤分類」，已在回報 open_questions，由 manager 之後補。

問題數量：0
