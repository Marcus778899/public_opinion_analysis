APPROVE 7ec9afc

# Review test-infra-fast-waits（PR #97，第 2 輪）

對照：派工單（含兩則追加）、開發規格 7.26、D-015、backend-standards 第 6 節。重新讀過 `gh pr diff 97` 的全部內容（3 個 commit），不只看上一輪的 6 點；也讀了 worktree 裡的 `tests/integration/conftest.py`、`test_parallel_isolation.py` 與 `infra/clickhouse/migrations/*`。CI run 39410328849（head 7ec9afc）的 Check、Integration Test（1m56s）、Security 都是綠的；qa 結果 PASS 7ec9afc。

## 上一輪 6 點（a0b68bf..7ec9afc 只改了 `docs/development-spec.md`）

| # | 結果 |
|---|---|
| 1 威脅表要補 cluster_id | 已修：1193 行補了比對 `cluster_id`，也寫出主機允許清單擋不住 `localhost:9092` 的理由 |
| 2 全域重置寫了兩次 | 已修：1164 行改成 flock 的寫法，「全域重置的協調」那列刪掉了 |
| 3 ClickHouse worker DB 寫了兩次 | 已修：1167 行改成 `without_kafka`，重複的那列刪掉了 |
| 4 做法 8 與順序 1 的重置順序過時 | 已修：做法 8 改成刪 `radar_it_*` worker DB 與 slot、比對在刪除之前、`is_current` 時保留 3 個 topic（引用 ④）；順序 1 的補充加註「已由順序 2 取代」 |
| 5 xdist_group 規則前後不一 | 已修：風險表跟隔離表統一，並引用隔離表 |
| 6 進度表與 CI 數字 | 已修：進度表改成 ✅；1183 行補上 run 39409040277 的 1 分 56 秒，並註明只改文件的情況沒有實測 |

用 grep 找 `shared_topics`、`待 CI`、`尚未做`、`DROP SCHEMA`、`workerinput`，都沒有殘留。

## 整個 PR 的獨立檢查

| 項目 | 結果 |
|---|---|
| 範圍 | 15 個檔案都在負責檔案內；`src/`、ci.yml、`compose.ci.yaml`、`.env.example`、`scripts/`、`.claude/` 都沒動 |
| 受保護路徑 `compose.yaml` | 只改了 `CLUSTER_ID`（附 NOTE）和 `test` 的預設 command；沒有新增 volume、socket、port 或 privileged |
| 相依 | `pyproject.toml` 加了 `pytest-xdist>=3.8.0`；`uv.lock` 多了 pytest-xdist 與 execnet 兩個套件（D-015 已核可） |
| 驗收 ① 連跑兩次＋`-n 0` | qa 第 1 輪實際跑過，都是 150 passed；之後的 commit 只改文件 |
| 驗收 ② CI ≤ 3 分鐘、`--durations=15` | 1m56s；`--durations=15` 已加進 `make coverage` 與 `test` 服務的 command（CI 走 `make coverage`）。只改文件 ≤ 1 分鐘靠做法 12（順序 1 已做），回報有寫依據 |
| 驗收 ③ cluster_id 防呆 | `_reset_global` 第一步就呼叫 `check_kafka_target`，PG 與 ClickHouse 都還沒刪；`reset_kafka` 內又檢查一次。有三種測試：mock 測試（cluster_id 不符時不呼叫 delete／create）、真 Kafka 配錯誤期望值（topic 保留）、靜態測試（compose 的值和 conftest 一致，且不同於 `.env.example`） |
| 驗收 ④ 開發環境不受影響 | 測試只讀 `IT_*`；PG 管理連線只接受 `radar_it`（`_pg_admin`），而且有測試證明連到 worker DB 時會拒絕；ClickHouse 刪除前都會先檢查目標是測試主機（`assert_test_clickhouse`、`is_test_host`）；回報有寫 `down -v` |
| SQL／識別字注入 | 組 DB 名稱的地方都先用 regex 或 isalnum 擋過（`worker_database`、`create_worker_database`、`create_worker_postgres`）；slot 名稱用參數綁定 |
| 平行隔離的正確性 | 上一輪判定的五處偏離維持「接受」（理由見上一輪，這次沒有新變更）。另外確認了 `without_kafka` 會略過所有 MV，而 0001～0004 的 MV 全都讀 `*_queue`（Kafka engine），所以結果和文件寫的「Kafka engine 表與讀它的 MV」一致；`test_migration_0003` 改用 `without_kafka` 之後，仍然測得到 0003 的 `INSERT … SELECT FROM comments` 複製邏輯 |
| 寫死的設定 | `CLUSTER_ID` 是測試 compose 裡的非機密固定值，有一致性測試保護；沒有其他寫死的值 |
| 文件與程式一致 | 7.26 的做法 8、隔離表、實作補充、威脅表、風險表都和 conftest／`_xdist.py` 的行為一致（qa 第 2 輪也逐項對照過） |

## 不阻擋的建議（之後再處理，不必在本單改）

- `tests/helpers/clickhouse.py` `without_kafka`：判斷方式是比對 `"CREATE MATERIALIZED VIEW"` 字串，會略過所有 MV。之後如果新增讀一般表的 MV，worker DB 會少了它，而且不會有任何提示。建議到時候改成只略過 `FROM *_queue` 的 MV，或加一個測試確認 MV 都讀 `*_queue`
- `is_current` 的剩餘風險和上一輪說的一樣：只重建 Kafka、沒有重建 ClickHouse 時，不會檢查 consumer 是否還正常。平常都是 `down -v` 一起清，影響很小

問題數：0
