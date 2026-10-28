PASS 7263cad

# dashboard-views 驗證證據

| 驗收條件 | 結果 | 證據 |
|---|---|---|
| 驗收測試全過（test_views.py 20 題） | 通過 | compose test 兩種模式都全過；驗收測試檔自 ecb0cc9 起沒被改（`git diff ecb0cc9 HEAD -- tests/integration/acceptance` 為空） |
| `make check` | 通過 | `1110 passed in 4.28s`（pre-commit 通過） |
| compose test `-n auto`（預設指令） | 通過 | `8 workers [192 items]` … `192 passed in 57.60s` |
| compose test `-n 0`（`run --rm test pytest tests/integration -n 0 --durations=5`） | 通過 | `collected 192 items` … `192 passed in 128.24s (0:02:08)`；兩種模式結果一致，無 7.26 風險表所列的平行互相干擾 |
| down -v | 完成 | 容器、volume、network 全部 Removed |
| 設計 6.3、開發規格 7.25／7.26 與實作一致 | 一致 | 見下 |
| PR #105 CI | 全綠 | Check pass、Integration Test pass、Security pass；PR head = 7263cad，與驗證的 commit 相同 |

## 細節

- 0005：`git diff develop...HEAD --stat -- infra/clickhouse/migrations` 只有 `0005_dashboard_views.sql` 新增 22 行；0001～0004 沒動。兩個都是 `CREATE VIEW`（非 materialized）。
- view 邏輯與 `bot/stats.py` 的 `POST_STATS_QUERY` 對照：`comments_latest FINAL`、`is_deleted = 0`、`countIf(type=…)`、`argMax(…, predicted_at)`、`arrayMax(mapValues(scores))` 都相同。
- 設計文件 6.3 表新增兩列，欄位與 SQL 一致（post_votes：post_id、board、push、boo、arrow；post_sentiment_latest：post_id、model_version、polarity、score）。開發規格 7.25 新增欄位一行，與 SQL 一致。
- cdc 測試修改（`test_json_topic_rows_land_in_target_tables`）：labels、predictions 的兩個 `_wait_rows` 與兩個 SELECT 都加 `WHERE post_id = 'Stock.M.1.A.1'`，與仲裁檔逐項相符。期望值（兩列 labels、一列 predictions、text_hash 為空字串）沒變，alerts 斷言沒變，沒有放寬原本要驗的行為；只收窄到自己的資料。
- 開發規格 7.26 的 `radar` DB 一列改成「只看自己的 `post_id`／`unit_key`，任何測試都不可斷言整張表」，與仲裁建議一致。
- 變更檔案都在最後一則追加的負責檔案內，沒碰 `src/`、`scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`、grafana 設定。
- `grep -rn "TODO(dashboard-views)" src tests` 沒有結果。新增的 SQL 沒有寫死 port、網址、token。

## 備註（不影響判定）

- 本單是純 SQL view，沒有新的 Python 函式，所以沒有新增單元測試；行為由 acceptance test_views.py 覆蓋。
- 回報 `reports/dashboard-views.json` 的 open_questions 「PR 的 CI 尚未開」已過時（PR #105 已開且全綠）。
