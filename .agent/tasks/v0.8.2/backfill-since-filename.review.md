APPROVE 5df217b

## 檢查範圍

- `gh pr diff 302`（5 檔），對照派工單 `.agent/tasks/backfill-since-filename.md`、開發規格 7.30 E（含派工表第 3 列、自行決定表 `split_part` 列）、7.28 A
- 負責檔案：worker commit 5df217b 只改 `src/radar/collector/scheduler.py`、`tests/unit/collector/test_scheduler.py`、`tests/integration/collector/test_scheduler_since_db.py`（新），都在負責範圍；兩個驗收測試檔只在 qa commit 74de669 改過，worker 沒碰
- 沒有改 parser、`posts.created_at` 的寫法、文件；沒有寫死設定值；`TODO(backfill-since-filename)` grep 沒有結果
- CI：Check、Integration Test、Security 都通過（覆蓋率由 CI 的 coverage 步驟檢查）
- 本機：`PYTHONPATH=$(pwd)/src .venv/bin/python -m pytest -q -p no:xdist tests/unit/collector/test_scheduler.py tests/unit/acceptance/scheduler-statement-timeout` → `37 passed`

## 對照 7.30 E

| 規格 | 實作 | 判定 |
|---|---|---|
| `max(split_part(post_id,'.',3)::bigint)`，Core `select()` | `select(func.to_timestamp(func.max(cast(func.split_part(...), BigInteger))))` | 符合；數字比較，不是字串比較（驗收 `test_since_compares_epoch_numerically_not_as_text` 測到） |
| 轉 UTC 減 10 分鐘 | `to_timestamp` 回傳 timestamptz，psycopg 轉成帶時區的 datetime，跟 `datetime.now(UTC)` 比較與相減都正確 | 符合 |
| 晚於現在時以現在計並記 WARNING | `latest_at > current` → `log.warning` 後改用 `current` | 符合 |
| 刪除文仍計入、沒有文章為 null | 查詢沒有篩 `is_deleted`；`max` 沒有資料列回 NULL → None | 符合 |
| 查詢逾時照拋、其他失敗回 null（7.28 A） | except 區塊沒改 | 符合 |

## worker 提出的兩點

1. **SQL 裡用 `to_timestamp` 轉，不在 Python 端轉 epoch**：規格只規定「檔名 epoch 的最大值轉 UTC」，轉換放在 SQL 還是 Python 是實作細節，結果相同。這樣寫，既有驗收 `tests/unit/acceptance/scheduler-statement-timeout` 的 fake engine（`scalar_one` 回傳 datetime）不用改，也不會變成要另外仲裁的矛盾。接受。
2. **新增選填參數 `now`**：預設 `None` 時用 `datetime.now(UTC)`，唯一的呼叫端 `scheduler.py:151` `latest_post_since(engine, board)` 不受影響；backend-standards §6 要求時間可以注入，單元與整合測試也靠它把 clamp 測成固定值。接受。

## 測試有沒有測到驗收條件

- 真的 PG 上 since = 最大檔名時間 − 10 分鐘：驗收 `test_since_is_max_filename_epoch_minus_ten_minutes`、整合 `test_latest_post_since_uses_filename_epoch_not_created_at`
- `created_at` 在 2099 年不影響：`test_since_ignores_created_at_in_2099`
- 刪除文、沒有文章、未來檔名時間 clamp 加 WARNING：都有對應的驗收測試；單元測試 `test_latest_post_since_future_filename_is_clamped_to_now_with_warning` 涵蓋新增的分支

## 備註（不擋合併）

- `post_id` 第三段不是數字（或超過 bigint）時，cast 失敗會讓整個看板的查詢失敗，結果是回 null 並記 WARNING。依 CLAUDE.md，`post_id` 是 `<board>.<PTT 檔名>`，PTT 檔名固定是 `M.<epoch>.A.<hex>`，作者改不了，所以視為不會發生；退回去的路徑跟查詢失敗一樣，不會讓計時器停掉
