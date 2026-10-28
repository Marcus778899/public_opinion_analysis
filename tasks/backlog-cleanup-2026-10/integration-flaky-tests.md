# 派工單 integration-flaky-tests

- **類型**：test
- **負責**：backend
- **目標**：消除 4 個整合測試偶發失敗，CI 的 Integration Test 不用再重跑
- **背景**：#110 `common/test_producer_partition.py` 偶發 UNKNOWN_TOPIC_OR_PART（topic metadata 未傳播）；#111 `acceptance/dashboard/test_views.py`、`test_panels.py` 在 radar DB 放種子資料卻沒標 `xdist_group("shared_radar_db")`；#117 `cdc/test_slot.py` lag 斷言受其他 worker 寫入影響（issue 建議量自己 slot 的 confirmed_flush_lsn）；#126 `common/test_topics_apply.py` 偶發 `3 == 3+1`（原因未查）。各 issue 有 run 連結與重現細節
- **設計依據**：`docs/development-spec.md` 7.26（平行隔離表）、7.25；issue #110 #111 #117 #126
- **相依**：無
- **負責檔案**：
  - `tests/integration/common/test_producer_partition.py`
  - `tests/integration/common/test_topics_apply.py`
  - `tests/integration/cdc/test_slot.py`
  - `tests/integration/acceptance/dashboard/test_views.py`
  - `tests/integration/acceptance/dashboard/test_panels.py`
  - `tests/integration/conftest.py`
  - `docs/development-spec.md`（7.26 平行隔離表：拿掉「已鎖定，另開單由 qa 補標」，補上這次的修法）
- **禁區**：不改 `src/`（若根因在 src，停下來回報）；不刪測試、不放寬斷言到失去意義、不加固定 sleep 或 retry 掩蓋；不改 `tests/helpers/`（#98 另開單）；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 每個 issue 在回報寫出根因與修法（#126 要先查出原因）
  - [ ] `docker compose --env-file .env -f .worktrees/integration-flaky-tests/compose.yaml run --rm test` 在全新堆疊（先 `down -v`）連跑 3 次都全過，附輸出摘要
  - [ ] 以 `-n 0` 再跑一次也全過；做完 `down -v`
  - [ ] `make check` 通過；PR 的 CI 全綠
- **驗證指令**：`make check`；上面的 compose 指令
- **回報檔**：`reports/integration-flaky-tests.json`

## 執行資訊（task.py 產生）

- Issue：#129
- 分支：`test/integration-flaky-tests`（從 develop 開出）
- 工作目錄：`.worktrees/integration-flaky-tests`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-21

### reports/integration-flaky-tests.review.md

REQUEST_CHANGES c324a04

# Code review：PR #138（integration-flaky-tests）

## 檢查範圍

| 項目 | 結果 |
|---|---|
| 改到的檔案是否都在負責檔案內 | 是，7 個檔案都在清單內；`src/`、`tests/helpers/`、`scripts/` 都沒改 |
| #110 `test_producer_partition.py` | OK：用 `wait_until` 等 3 個 partition 都有 leader 才送；是條件輪詢，不是固定 sleep |
| #126 `test_topics_apply.py` | OK：等 `fetch_existing` 看到新的 partition 數再斷言；原本的斷言（`spec.partitions + 1`、retention）都沒放寬 |
| #111 `acceptance/dashboard/test_views.py`、`test_panels.py` | OK：標記名稱與既有的 `shared_radar_db` 一致；docstring 也同步改了 |
| `conftest.py` 的 `wait_until` fixture | OK：重用既有的 `_wait_until`（有 deadline、逾時丟 TimeoutError） |
| 開發規格 7.26 | OK：表格與新增的補充條目都和程式一致（還有一項小問題，見下方第 3 點） |
| 寫死設定值、安全 | 沒有新增 port、網址或 token |
| #117 `cdc/test_slot.py` | **有問題**，見下方 |

## 對 qa 兩項備註的判斷：要在這張單修

**①覆蓋缺口確實存在。** `read_slot`（`src/radar/cdc/watchdog.py:141`）回傳的 `lag_bytes` 來自 `_SLOT_QUERY`：
`pg_current_wal_lsn() - COALESCE(confirmed_flush_lsn, restart_lsn)`。
`SlotWatch.observe`（同檔 :121）用它判斷要不要發 LAGGING 告警。

- 單元測試 `tests/unit/cdc/test_watchdog.py` 都是直接建 `SlotInfo`，沒有跑過這段 SQL。
- 整合測試裡，只有這一條在驗「消費之後 lag 是對著 slot 已確認的位置算」。
- 改完之後，這條測試對 `read_slot` 只剩 `consumed.active is False`，而前一條測試已經驗過 `active`。
- 新增的 `confirmed_flush_lsn` 斷言驗的是 PostgreSQL 的 `pg_logical_slot_get_changes` 本身，不是專案的程式。

舉例：如果 `_SLOT_QUERY` 被改成以 `restart_lsn` 算，或忘了 COALESCE 的順序，消費後 lag 不會下降、會一直誤發告警，而這兩組測試都抓不到。

這等於派工單禁區說的「放寬斷言到失去意義」。可以在不受其他 worker 寫入影響的前提下補回來，做法見下方。

**②名稱與斷言不符**：要一起修。補回 lag 的斷言之後，名稱 `lag_drops` 就又成立了，或者依新的斷言改名。

## 要修改的地方

1. `tests/integration/cdc/test_slot.py:87-91` — 問題：消費後沒有斷言 `read_slot` 的 `lag_bytes`，`_SLOT_QUERY` 的 lag 計算沒有被任何測試真的執行並驗證。
   - 修法：在同一個連線裡，呼叫 `read_slot` 前後各讀一次 `pg_current_wal_lsn()`（記為 `w1`、`w2`），再讀自己 slot 的 `confirmed_flush_lsn`（記為 `c`），斷言 `w1 - c <= consumed.lag_bytes <= w2 - c`。
   - 用 `pg_wal_lsn_diff` 換算成 byte。上下界都以自己 slot 的位置為基準，其他 worker 的寫入只會同時推高 `w1`、`w2`，所以斷言不會偶發失敗。
   - 保留現有的「`confirmed_flush_lsn` 前進 > 400_000」斷言。兩者合起來，就是「消費後 lag 以自己 slot 已前進的位置計算」。
   - 不可以加 sleep、retry 或 xdist_group 來繞過。
2. `tests/integration/cdc/test_slot.py:75` — 問題：測試名稱 `..._lag_drops` 和目前的斷言不符。
   - 修法：做完第 1 點後，改成能描述新斷言的名稱，例如 `test_read_slot_after_consuming_changes_lag_measured_from_confirmed_flush`。
   - 如果第 1 點的斷言確實表達「lag 因消費而下降」，也可以保留原名，但要在回報裡說明理由。
3. `docs/development-spec.md:1190`（非阻擋，建議順手改）— 問題：「實作補充（順序 2）②」還寫著 `cdc/test_slot` 的 lag 斷言是「降了至少 400 KB」，這和現在的實作不符；新增的條目③只是補述，舊的那句沒改。
   - 修法：在舊句後面加「（已由 `integration-flaky-tests` ③ 取代）」，或改寫那一句。

## 其他（不影響判定）

- qa 因為主機記憶體不足，沒有親手跑完「全新堆疊連跑 3 次」與「`-n 0` 全套」，改用 PR CI 全綠加上受影響的子集作輔證。修完第 1 點後，`cdc/test_slot.py` 至少要在全新堆疊用 `-n 8` 與 `-n 0` 各跑一次。

- 本機 Docker 記憶體有限：重跑全套整合測試時先確認沒有其他測試堆疊在跑，資源不足造成的失敗請在回報註明，不要為此改斷言。
