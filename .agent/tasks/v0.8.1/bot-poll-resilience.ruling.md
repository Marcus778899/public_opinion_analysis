TEST_WRONG dfa9c8c

# 仲裁：bot-poll-resilience 驗收測試

觸發：worker 回報 disputes（`reports/bot-poll-resilience.json`）。依據：派工單 `tasks/bot-poll-resilience.md` 的驗收條件（本單沒有 docs/contracts 契約，以派工單驗收條件當契約）。

## 測試檔來源

`tests/unit/acceptance/bot-poll-resilience/` 只有 qa 的 `ee82d2e test(bot-poll-resilience)` 改過，worker 的 `dfa9c8c` 沒有碰測試，worktree 沒有未提交的修改。

## 實際執行（worktree，HEAD dfa9c8c）

| 指令 | 結果 |
|---|---|
| `uv run pytest -p no:randomly tests/unit/acceptance/bot-poll-resilience/` | 1 failed（`test_purge_pg_down_loop_keeps_running_and_logs_warning`），9 passed |
| 單獨跑 `…::test_purge_pg_down_loop_keeps_running_and_logs_warning` | failed；captured stderr 有 `WARNING … purge_muted failed (PG unavailable), retry next round` |
| 單獨跑 `…::test_update_unexpected_error_is_logged` | failed；captured stderr 有 `WARNING … update 10 skipped after unexpected error: RuntimeError('boom-marker')` |
| `uv run pytest tests/unit/acceptance/bot-poll-resilience tests/unit/bot`（派工單驗證指令） | 1 failed，197 passed |
| `make check` | 1665 passed，exit 0（全套件跑時，前面的測試已經建好 logger） |

## 原因（已重現，屬實）

- `loggerhelper.Logger` 第一次寫 log 時才 `_build()`，並設 `propagate = False`。
- pytest 9.1.1 的 `catching_logs.__enter__`（`_pytest/logging.py` 約 350–366 行）在每個 phase 開始時，把 capture handler 掛到 root 和「當時已存在、propagate=False」的 logger；原始碼註解寫明會漏掉之後才變成 non-propagating 的 logger。
- 所以在這個行程裡，第一個寫 log 的測試，它的 call phase 開始時 `loggerhelper` logger 還不存在，caplog 收不到任何紀錄；之後的測試才收得到。結果取決於執行順序，跟實作無關。CI 的 `make coverage` 用 `-n auto`，每個 worker 的順序不固定，也可能失敗。
- 依專案規範，log 一律要走 `radar.common.log.log`，所以任何符合規範的實作都過不了這兩個測試的單獨執行。

## 逐條判定

| 測試 | 契約條文 | 判定與理由 |
|---|---|---|
| test_purge_pg_down_loop_keeps_running_and_logs_warning | 驗收條件 1：PG 斷線「記 WARNING 後重試」 | **測試錯**。要驗的事對，但 caplog 量不到實作確實寫出的 WARNING（stderr 可見），結果看執行順序 |
| test_update_unexpected_error_is_logged | 驗收條件 2：意外例外「記錄後跳過」 | **測試錯**，原因相同（沒排在第一個才通過） |
| 其餘 8 個測試 | 驗收條件 1～3 | 符合契約，不用改；目前全過 |

## 測試要怎麼改（qa）

只改同檔的 `warnings` fixture：在 setup phase 先寫一行 log，讓 loggerhelper 的 logger 先建好，call phase 的 caplog 才掛得上去。斷言不動：

```python
@pytest.fixture
def warnings(caplog):
    from radar.common.log import log

    log.debug(
        "caplog warm-up"
    )  # NOTE: loggerhelper 第一次寫 log 才建 logger（propagate=False），先建好 caplog 才掛得上
    caplog.set_level("WARNING")
    return caplog
```

我拿副本驗證過這個改法：

- 兩個測試單獨跑都 passed，整個檔案 10 passed。
- 反向檢查：把 `bot_main.log` 的 warning、error、exception、info 換成 no-op 以後，兩個測試都 failed，代表測試仍然會抓到沒寫 log 的實作。

## 契約問題

- 無。（附帶一提：其他驗收目錄如果之後也用 caplog 驗 loggerhelper 的 log，會踩到同一個坑；可以考慮在 `tests/unit/acceptance/conftest.py` 加共用 fixture，那支檔案歸 architect，需要另開單。）
