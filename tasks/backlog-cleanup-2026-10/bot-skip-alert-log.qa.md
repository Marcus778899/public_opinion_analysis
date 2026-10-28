PASS bc5ec03

# 驗證 bot-skip-alert-log（PR #133，head bc5ec0388fa2，與驗證的 commit 一致）

## 驗收條件對照

1. 被通知設定略過時有一行 INFO log（radar.common.log）：PASS
   - `filter_recipients`（repository.py）對每個被略過的 chat 記 `alert <id> (<unit_type> <unit_key>) skipped for chat <chat>: <原因>`，原因為 `chat_settings disabled` 或 `post muted`；正常送出不記這行。
   - 多個原因並存時只記先判斷到的 `chat_settings disabled`（worker 已在回報說明）。
2. 單元測試涵蓋被略過有 log、沒被略過沒有 log：PASS
   - `tests/unit/bot/test_repository.py` 4 項：disabled 被略過且有 log、muted 被略過且有 log、沒有被略過時 log 為空、空輸入。
   - 備註：派工單列的 test_notify.py／test_main.py 沒改，因為邏輯移到 repository，合理。
3. `make check` 通過：PASS（原始輸出尾端：`1118 passed in 8.18s`）；`ruff check .` 為 `All checks passed!`；`ruff format --check .` 為 `253 files already formatted`；`pytest tests/unit/bot` 為 `185 passed`。
4. PR CI（`gh pr checks 133`）：
   - Check pass（34s）
   - Integration Test pass（2m9s）
   - Security fail：既有問題。develop 的 gitleaks 因封存檔誤判而紅燈，由 PR #134 另修，與本 PR 無關，不列為 FAIL。

## 重點：送給誰、略過誰的結果與修改前完全一致

比對 diff（`git diff develop...HEAD -- src`）：

- 原 SQL：`(chat_settings 無列 OR 該開關 IS TRUE) AND NOT muted（僅 post）`。
- 新 SQL 取回 `(chat_id, 開關, muted)`，改由 Python 過濾：`開關 is False` 略過、`muted` 略過，其餘保留。
- `muted` 對 board 警示固定為 `literal(False)`，與原本 board 不檢查 mute 一致。
- 開關為 None（無 chat_settings 列）保留，與原本一致。
- `chat_settings.post_alerts`、`board_alerts` 在 model 為非 Optional bool（NOT NULL），所以「有列但開關為 NULL」不會發生。
- 仍是一次查詢，沒有對每個 chat 另外查 PG；不寫 PG，不改 schema。
- 排序維持 `ORDER BY chat_id`。
- notify.py、main.py 未改，`recipients` 回傳型別不變。

行為證明：既有整合測試 `tests/integration/bot/test_preference_repository.py::test_recipients_filters_subscription_type_and_mute` 同時涵蓋 post 關閉、board 關閉、mute 與跨看板訂閱，斷言 post 為 `[1, 3]`、board 為 `[1, 2, 4]`，沒有修改。我在 worktree 實跑：

```
docker compose --env-file .env -f .worktrees/bot-skip-alert-log/compose.yaml run --rm test pytest tests/integration/bot -p no:cacheprovider -q
22 passed in 34.83s
```

## 整合測試全套（需註明）

我自己跑一次全套 `run --rm test`，結果 `89 failed, 219 passed, 21 errors in 602.50s`。失敗全部在 ClickHouse、Grafana、dashboard 相關檔：

- tests/integration/acceptance/dashboard
- dashboard
- cdc/test_clickhouse_migrations
- common/test_topics_apply
- test_parallel_isolation
- bot/test_stats_clickhouse 的 error

錯誤是 `Name or service not known`、`lookup clickhouse ... server misbehaving`、`Connection reset by peer`，也就是本機 docker 在跑到一半時 ClickHouse 容器連線掉了。這些檔案與本 PR 修改無關（本 PR 只動 bot/repository）。同一個 commit 在 CI 的 Integration Test 為 pass，worker 本機回報 329 passed，因此判為環境問題而非本 PR 的回歸。bot 的 PG 整合測試單獨重跑全過（上方 22 passed）。

## 其他檢查

- `grep TODO(bot-skip-alert-log) src tests`：無結果。
- 沒有寫死的 port、網址、token。
- Log 使用 `from radar.common.log import log`，沒有 print 或標準 logging。
- 已用 `down -v` 關掉我啟動的容器。

## 非阻擋觀察（不構成 FAIL）

- 被「不再通知」（muted）略過時也會記一行 INFO，超出派工單字面的「通知設定」，但屬同類資訊，不影響送出結果。
- log 放在 repository 層，不在 notify.py；與追加的方案 A 一致。

問題數量：0
