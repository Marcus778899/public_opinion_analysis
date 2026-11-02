APPROVE 0d62e95

# Code review：PR #138（integration-flaky-tests，第 2 輪）

PR head `0d62e9577d63`，與 worktree HEAD 相同。這一輪看 `git diff c324a04 0d62e95`，也重新看了整張單的 diff（`develop...HEAD`，7 個檔案）。

## 上一輪退回的 3 條

| # | 退回內容 | 結果 |
|---|---|---|
| 1 | `test_slot.py` 消費後要斷言 `read_slot` 的 `lag_bytes` | 已處理，結果 OK。程式在 `test_slot.py:90-101`：<br>• 同一個連線裡，在 `read_slot` 前後各讀一次 `pg_current_wal_lsn()`（`wal_before`、`wal_after`）。<br>• 斷言 `wal_before - flushed_after <= consumed.lag_bytes <= wal_after - flushed_after`。<br>• 保留了 `flushed_after - flushed_before > 400_000`。<br>• 沒有加 sleep、retry 或 xdist_group。<br>上下界都以自己 slot 的 `confirmed_flush_lsn` 為基準，這個值消費之後就不會再變（只有本測試會消費這個 slot），所以其他 worker 的寫入不會讓斷言失敗。`_SLOT_QUERY`（`src/radar/cdc/watchdog.py:130`）的 lag 計算真的有被執行，結果也有被驗證。 |
| 2 | 測試名稱要和斷言一致 | 已處理，結果 OK：改名為 `test_read_slot_after_consuming_changes_lag_measured_from_confirmed_flush` |
| 3 | 開發規格 7.26 的舊句 | 已處理，結果 OK：在實作補充②的舊句後面加了「已由 `integration-flaky-tests` 取代」，條目③也補上了上下界斷言的說明，內容和程式一致 |

## 整張單

| 項目 | 結果 |
|---|---|
| 負責檔案 | 7 個檔案都在清單內；`src/`、`tests/helpers/`、`scripts/` 都沒改 |
| #110、#126 | 用 `wait_until`（有 deadline）等條件成立；沒有新增固定 sleep；原本的斷言沒有放寬 |
| #111 | 補上了 `xdist_group("shared_radar_db")`，名稱和既有的群組一致 |
| #117 | 見上表第 1 條 |
| 寫死設定值、安全 | 沒有新增 port、網址或 token |
| 驗證 | 我自己跑了 `make check`：1114 passed。`gh pr checks 138`：Check、Integration Test、Security 都 pass。qa 證據顯示：全新堆疊連跑 3 次全過、`-n 0` 全套全過、做完有 `down -v` |
| 回報 | open_questions 裡寫了 4 個 issue 各自的根因與修法 |

## 非阻擋建議

- `tests/integration/cdc/test_slot.py:58`：`current_wal(conn)` 的參數少了型別標註（CLAUDE.md 規定全部使用 type hints），應該寫成 `conn: Connection`。ruff 的設定沒有擋到這個問題。可以之後再順手修，不影響這次的判定。
