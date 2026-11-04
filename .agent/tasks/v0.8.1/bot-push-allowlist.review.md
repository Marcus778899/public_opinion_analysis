APPROVE 76c154e

# Review bot-push-allowlist（PR #247）

比對：`git diff develop...76c154e`（與 `gh pr diff 247` 檔案清單一致，共 3 檔）。

## 檢查項目

| 項目 | 結果 |
|---|---|
| 負責檔案 | `src/radar/bot/main.py`、`tests/unit/bot/test_main.py`；驗收測試目錄只有 qa 的 `test(bot-push-allowlist)` commit 8c103bd 改過。模組層級 `filter_recipients` 超出「只限 main()」，manager 已接受 |
| D-010 | 過濾沿用 `is_allowed`：清單有設只送清單內 chat；清單空（`check_allowlist` 只在 `TELEGRAM_ALLOW_ALL=true` 時放行空清單）全送；清單有設時忽略 ALLOW_ALL，與 `check_allowlist` 既有規則一致。`is_allowed`、`check_allowlist`、指令處理、callback 未改 |
| 訂閱資料 | `recipients()` 只呼叫 `PreferenceRepository.recipients`（唯讀）；未改 `repository.py`、無 migration。被過濾的 chat 不進 `AlertNotifier._deliver`，因此也不會觸發 `forget_chat`（刪訂閱只在 Telegram 回 403 時發生，既有行為） |
| 冪等／commit | 過濾在 `_recipients` 之後、`_sent.add` 之前；全部被過濾時 `chats` 為空，照舊記為已處理，不重送、不 DLQ，行為正確 |
| log | 只記被過濾的人數（INFO），不記 chat id 或其他個資 |
| 寫死設定 | 無；清單取自 `settings.allowed_chat_ids` |
| 測試是否測到驗收條件 | 驗收測試從 `main()` 組出的 handler 實際推送：只送清單內、訂閱資料無其他呼叫、清單無交集不送、ALLOW_ALL 無清單全送、ALLOW_ALL＋清單仍過濾、log 人數。單元測試涵蓋過濾、空清單、無訂閱者 |
| 驗證（本次實跑） | `PYTHONPATH=src uv run pytest -q tests/unit/acceptance/bot-push-allowlist tests/unit/bot` → 200 passed；`uv run ruff check src tests` → All checks passed!；`grep -rn "TODO(bot-push-allowlist)" src tests` → 無結果 |

## 備註（不擋合併）

- 開發規格需補「推送也照允許清單過濾」，worker 已列進回報 open_questions，交 spec-docs-sync。
