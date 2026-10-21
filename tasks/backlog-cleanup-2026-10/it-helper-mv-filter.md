# 派工單 it-helper-mv-filter

- **類型**：test
- **負責**：backend
- **通道**：fast
- **目標**：整合測試 helper 的 `without_kafka` 只略過讀 Kafka 的 MV，`is_current` 判斷涵蓋 Kafka engine consumer
- **背景**：test-infra-fast-waits（PR #97）review 的非阻擋建議（#98）：① `tests/helpers/clickhouse.py` 的 `without_kafka` 以 "CREATE MATERIALIZED VIEW" 字串判斷，會略過所有 MV，之後新增讀一般表的 MV 時 worker DB 會靜默少一個；② `is_current` 為 True 時只清資料表，不檢查 Kafka engine consumer，只重建 Kafka 沒重建 ClickHouse 時可能失效
- **設計依據**：`docs/development-spec.md` 7.26；issue #98
- **相依**：無
- **負責檔案**：
  - `tests/helpers/clickhouse.py`
  - `tests/unit/helpers/__init__.py`
  - `tests/unit/helpers/test_clickhouse_helper.py`
- **禁區**：不改 `src/`、`tools/`、migration 檔；不改 `tests/integration/`（另一張單 integration-flaky-tests 正在改）；②若要連真 ClickHouse 才能驗證，在回報說明並以單元測試涵蓋判斷邏輯即可；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] `without_kafka` 只略過 `FROM *_queue`（Kafka engine 表）的 MV；讀一般表的 MV 保留；單元測試涵蓋兩種
  - [ ] `is_current` 在 Kafka engine 表或 consumer 狀態不對時回 False（或回報說明為何不可行與替代做法）；單元測試涵蓋
  - [ ] `docker compose --env-file .env -f .worktrees/it-helper-mv-filter/compose.yaml run --rm test` 全過，做完 `down -v`
  - [ ] `make check` 通過；PR 的 CI 全綠
- **驗證指令**：`make check`；上面的 compose 指令
- **回報檔**：`reports/it-helper-mv-filter.json`

## 執行資訊（task.py 產生）

- Issue：#137
- 分支：`test/it-helper-mv-filter`（從 develop 開出）
- 工作目錄：`.worktrees/it-helper-mv-filter`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
