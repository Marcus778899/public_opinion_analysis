PASS 7ec9afc

# QA test-infra-fast-waits（PR #97，第 2 輪）

範圍：a0b68bf 之後的變更是否只有文件、review 6 點是否改好且與程式一致、最新 commit 的 CI。程式沒變，沿用第 1 輪（a0b68bf）的整合測試實跑證據（`-n auto` 兩次、`-n 0` 一次，皆 150 passed），本輪未重跑。

## 1. a0b68bf..7ec9afc 只有文件

```
$ git log --oneline a0b68bf..HEAD
7ec9afc docs(test-infra-fast-waits): 7.26 修正與 review 6 點一致
$ git diff --stat a0b68bf..HEAD
 docs/development-spec.md | 18 ++++++++----------
 1 file changed, 8 insertions(+), 10 deletions(-)
```

`git status --short` 無未提交變更。

## 2. review 6 點逐項對照（文件 vs 程式）

| # | 修改 | 與程式一致的依據 |
|---|---|---|
| 1 | 威脅表「開發環境的資料」補 cluster_id 比對與 `localhost:9092` 說明 | `tests/integration/conftest.py` `check_kafka_target`；`_reset_global` 第一步呼叫 |
| 2 | 1164 改 flock 寫法，刪除重複的「全域重置的協調」列 | `_xdist.py` `run_once`：`PYTEST_XDIST_TESTRUNUID` 為鍵、`fcntl.flock`、`.failed` 存在時 `pytest.exit`；註解 NOTE 說明不用 `pytest_sessionstart` |
| 3 | ClickHouse 列改 `without_kafka`，刪除重複列 | `test_clickhouse_migrations.py:212,218` 使用 `without_kafka`；做法 9 的 `*_queue` 刪除仍對應 `drop_queue_tables`（line 243），未矛盾 |
| 4 | 做法 8 改為刪 `radar_it_*` worker DB 與未使用 slot、比對在刪除前、`is_current` 時保留 3 個 topic（見補充 ④）；順序 1 註明已由順序 2 取代 | `_reset_global`：`check_kafka_target` → `reset_postgres` → `is_current` 分支（`reset_keeping_radar` + `reset_kafka(keep=CLICKHOUSE_TOPICS)`）否則 `drop_databases` → `reset_kafka` → `wait_clickhouse_groups_empty` → `apply_migrations`；`PG_WORKER_PREFIX = "radar_it_"` |
| 5 | 風險表 xdist_group 規則統一為「固定名稱 topic 且斷言整張表／整個 topic 時才需要標」 | 與 1168 行相同；程式只有 `test_clickhouse_migrations` 標 `shared_radar_db` |
| 6 | 進度表改 ✅；1183 行補 CI run 39409040277 的 1 分 56 秒（`1216 passed in 77.55s`），並註明只改文件 ≤ 1 分鐘未實測 | 第 1 輪 CI 紀錄；本輪新 run 的 Integration Test 耗時 1m56s（見下），數字吻合 |

`grep` 確認已無「待 CI 驗證」「pytest_sessionstart 中判斷」「刪掉 `*_queue` 表」（worker DB 那列）等舊敘述殘留。

## 3. PR #97 最新 commit 的 CI

```
$ gh pr view 97 --json headRefOid  -> 7ec9afcd78fb9534634f52b9f9fc4ad4a9d462d4
$ gh run view 39410328849 --json jobs
Check             success  10:46:47 -> 10:47:33
Integration Test  success  10:46:47 -> 10:48:43   (約 1m56s)
Security          success  10:46:47 -> 10:47:12
```

三個 job 全綠，run 的 headSha 與 PR head 相同。

## 問題

0 個。
