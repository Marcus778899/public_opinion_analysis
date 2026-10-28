APPROVE 7263cad

# Review：dashboard-views（PR #105）

依據：派工單 `tasks/dashboard-views.md`（負責檔案以 2026-10-21 追加為準）、開發規格 7.25／7.26、設計文件 6.3、仲裁 `reports/dashboard-views.ruling.md`。

## 檢查項目

| 項目 | 結果 | 說明 |
|---|---|---|
| 改動範圍 | 符合 | 5 個檔：4 個負責檔案，加上 qa 的驗收測試 `test_views.py`（ecb0cc9，qa 的 commit）；`git diff ecb0cc9 HEAD -- tests/integration/acceptance` 是空的，worker 沒改到驗收測試。0001～0004、`src/`、grafana 設定都沒動 |
| `post_votes` 對照 7.25 | 符合 | `comments_latest FINAL`、`is_deleted = 0`、`countIf(type = 'push'/'boo'/'arrow')`，跟 `POST_STATS_QUERY` 的 c 子查詢一樣；多一個 `board` group key，`board` 是從 `post_id` 推出來的（0003），不會讓一篇拆成兩列 |
| `post_sentiment_latest` 對照 7.25 | 符合 | `argMax(polarity, predicted_at)`、`argMax(arrayMax(mapValues(scores)), predicted_at)`，跟 `POST_STATS_QUERY` 的 s 子查詢一樣；另外多了 `model_version`，7.25 有要求這個欄位。不是 materialized view，也沒有改到既有的表 |
| migration 套用 | 符合 | 表名沒有寫 schema 前綴，會照連線的 DB 解析，所以 `radar_<worker>`、`hash_test` 這些 DB 也會建在自己的 DB 裡；`without_kafka` 只會略過 `ENGINE = Kafka` 和 `CREATE MATERIALIZED VIEW`，一般 view 照樣會建；`CREATE VIEW IF NOT EXISTS` 重複跑結果一樣。ClickHouse migration 本來就沒有 down，跟 0001～0004 一致，view 可以直接 DROP，可以回復 |
| 唯讀帳號 | 符合 | `users.d/grafana.xml` 是 `readonly=1`，而且只能用 `CLICKHOUSE_DB`；一般 view 是用呼叫者的權限去讀底層表，底層表也在同一個 DB 裡；驗收測試就是用唯讀帳號查，CI 已經通過 |
| 查詢效能 | 可接受 | 用 `post_id`、`board` 過濾時，條件會推進 view 裡（兩個都是 GROUP BY key），`post_id` 也是 `comments_latest`／`predictions` 的排序鍵第一欄。面板 4、6 用 join 時，條件不會推進 view，所以每次更新都會把整個 `comments_latest FINAL` 算一遍。以每天數千篇來看，幾個月後是百萬列等級的 FINAL 加 GROUP BY，在 `max_execution_time=60`、2 GB 的限制內；這跟 7.25「慢了再加 MV」的做法一致，不擋這張單 |
| cdc 測試修改 | 符合仲裁 | 只有兩個 `_wait_rows` 和兩個 `SELECT` 加上 `WHERE post_id = 'Stock.M.1.A.1'`（就是這個測試自己送出的訊息的 post_id）；期望值沒改，alerts 的斷言也沒動，驗證沒有放寬 |
| 文件同步 | 符合 | 設計文件 6.3 的表格加了兩個 view 和它們的欄位；開發規格 7.25 寫了欄位和 LEFT JOIN 的語意，7.26 的 `radar` DB 一列照仲裁改了 |
| 寫死設定、安全 | 沒有問題 | SQL 是固定的 DDL，沒有外部輸入；沒有新的設定值 |
| 驗收條件 | 達成 | qa `PASS 7263cad`；CI 的 Check、Integration Test、Security 都綠 |

## 不擋合併的備註

- `post_sentiment_latest` 的三個欄位各自用 `argMax`：同一篇如果有兩筆的 `predicted_at` 完全相同（微秒精度），三個欄位可能各自取到不同列。bot 也是這樣寫，這次照 7.25 收斂沒有錯；以後如果要修，改成 `argMax(tuple(model_version, polarity, score), predicted_at)`，bot 也要一起改。
- 開發規格 7.25 新加的「欄位：…」一行，跟上面兩個子項目的欄位清單重複了；之後動到這一段時可以合成一處。
