PASS 76c154e

# QA bot-push-allowlist (PR #247)

## 驗收條件
1. 有清單只送清單內：`main()` 的 `recipients` 經 `filter_recipients(subscribed, settings.allowed_chat_ids)`；實測 `filter_recipients([1,2,3],[2])` -> `[2]`。訂閱資料只讀（PreferenceRepository.recipients），無寫入。PASS
2. `TELEGRAM_ALLOW_ALL=true`：check_allowlist 要求清單為空才生效，空清單 -> `is_allowed` 不限制 -> 全送（測試 test_filter_recipients_empty_allowlist_keeps_all）。清單有設時 ALLOW_ALL 被忽略（既有行為，仍過濾）。PASS
3. log：只有 `log.info("push skipped %d subscriber(s) not in allowlist", n)`，僅人數，無 chat id 或其他個資。實測輸出 `push skipped 2 subscriber(s) not in allowlist`。PASS
4. 測試與檢查（PYTHONPATH 指向 worktree src，已確認 import 自 worktree）：
   - `uv run pytest tests/unit/acceptance/bot-push-allowlist tests/unit/bot` -> 200 passed
   - `uv run pytest tests/unit` -> 1719 passed
   - `pre-commit run --all-files` 全部 Passed（含 ruff、format、bandit）；ruff check / format --check 通過
   - `grep -rn "TODO(bot-push-allowlist)" src tests` 無結果。PASS

## 禁區
diff 只有 src/radar/bot/main.py（新增 filter_recipients + recipients 內 3 行）、tests/unit/bot/test_main.py、驗收測試。`is_allowed`、`check_allowlist`、指令、callback、PG 訂閱資料、開發規格皆未改。PASS

## filter_recipients 行為
過濾用 `is_allowed`，保持順序；空清單全保留；無訂閱者回空；被過濾數 > 0 才記 INFO。行為正確，小幅擴張可接受。

## 備註（非 FAIL）
開發規格需補的三點已在回報 open_questions，交 spec-docs-sync。
