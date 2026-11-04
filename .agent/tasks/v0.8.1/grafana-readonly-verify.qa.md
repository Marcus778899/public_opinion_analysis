PASS 141c32f

# 驗證證據：grafana-readonly-verify（PR #249）

變更只有 `tests/integration/dashboard/test_grafana_readonly.py`（+157 行），`grafana.xml` 未動。結論「不需收緊」我獨立驗證成立。有一項回報敘述不準確（見「注意事項」），不影響驗收條件，但寫進開發規格 7.25 前要更正。

## 驗收條件

1. 整合測試實測讀／寫／DDL／system／table function：PASS
   - 指令：`docker compose --env-file .env -f .worktrees/grafana-readonly-verify/compose.yaml run --rm test pytest tests/integration/dashboard tests/integration/acceptance/dashboard -q`
   - 輸出：`234 passed in 20.43s`（含新檔與既有 dashboard 整合與驗收測試）
2. 權限過寬才收緊 grafana.xml，既有 dashboard 驗收仍通過：PASS。實測沒有過寬，沒改設定；既有 `tests/integration/acceptance/dashboard/` 在上面那次一起通過。
3. 回報附指令與輸出、down -v：PASS。回報有指令；我另外跑了 `docker compose ... down -v`，容器、網路、volume 全部移除。
4. `make check`：PASS。我自己跑，輸出結尾 `1709 passed in 91.68s`（pre-commit 先通過）。`ruff check` 與 `ruff format --check` 對新檔也通過。

## 我自己用 grafana 帳號補測（`docker compose ... exec -T clickhouse clickhouse-client --user grafana ...`，ClickHouse 26.8.19）

全部符合預期，沒有繞過：

| 操作 | 結果 |
|---|---|
| `INSERT INTO radar.posts_latest` | READONLY (164) |
| `CREATE TABLE radar.t` | READONLY |
| `SELECT count() FROM system.users` | ACCESS_DENIED (497) |
| `view(SELECT * FROM system.users)`、與 `system.users` 做 JOIN | ACCESS_DENIED |
| `url()`、`file()`、`remote()`、`s3()`、`urlCluster`、`fileCluster`、`s3Cluster`、`deltaLakeCluster`、`cluster()` | ACCESS_DENIED（READ ON URL／FILE／REMOTE／S3） |
| `redis()`、`sqlite()`、`mongodb()`、`ytsaurus()`、`arrowFlight()`（新測試沒涵蓋） | ACCESS_DENIED |
| `dictionary('x')` | READONLY |
| `system.server_settings`、`errors`、`asynchronous_metrics`、`dictionaries` | ACCESS_DENIED |
| `--readonly=0`（INSERT）、`SETTINGS allow_introspection_functions=1` | READONLY（設定不可改） |
| `SETTINGS max_execution_time=61` | SETTING_CONSTRAINT_VIOLATION |
| `--database system` 之後 `SELECT name FROM tables` | 只列出 radar 的 23 張表 |
| 可讀（低風險） | `system.contributors`、`system.settings`（無憑證）、`generateRandom`、`numbers()` |

## 不依賴 .env、無寫死密碼

- 新檔只讀 `IT_CLICKHOUSE_URL`、`CLICKHOUSE_GRAFANA_USER`、`CLICKHOUSE_GRAFANA_PASSWORD`。這三個都由 `compose.yaml` 的 test 服務注入，不讀 `.env`。
- 預設值 `"grafana"` 與 `"it"` 是測試專用值，與 compose 一致，也與既有 `acceptance/dashboard/test_panels.py`、`test_views.py` 的寫法相同。這不是正式密碼，可接受。
- 若在 compose 之外直接跑，會退回這個預設值。

## 注意事項（不阻擋，manager 寫 7.25 前請更正）

回報 open_questions 說「真正的防護是 grafana 帳號未被授予各 READ/SELECT 權限（SHOW GRANTS 可見）」。這與實測不符：

- `SHOW GRANTS` 顯示 grafana 有 `FILE, URL, REMOTE, S3, MONGO, REDIS, MYSQL, POSTGRES, SQLITE, ODBC, JDBC, HDFS, ... SOURCES ON *.*`。
- `system.grants` 也有 `SOURCES`、`READ` 等列。
- 但實際查詢仍被拒絕。所以擋住 table function 與 system 表的是 `readonly=1` 的限制，加上 `allow_databases`，不是「沒給權限」。
- 影響：若有人把 profile 的 `readonly` 改成 2、或移除，table function 與 system 表的防護會一起消失。7.25 應寫「靠 readonly=1」，並註明新測試是升版與改設定的回歸防線。
- 這與 `grafana.xml` 現有的註解與設計一致，不需改設定。

## 未涵蓋（低風險，供參考）

- `*Cluster` 類 table function 在測試環境沒有叢集；我實測 `s3Cluster`、`urlCluster`、`fileCluster`、`deltaLakeCluster` 在權限檢查就被拒，已覆蓋。
- 資源濫用（記憶體、查詢數）只靠 profile 的 `max_memory_usage` 與 quota，新測試沒驗；範圍外。
