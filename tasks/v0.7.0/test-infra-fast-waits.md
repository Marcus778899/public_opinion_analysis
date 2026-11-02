# 派工單 test-infra-fast-waits

- **類型**：chore
- **負責**：backend
- **目標**：整合測試用 pytest-xdist 平行跑、去掉固定等待，讓 CI 的 Integration Test 變快（開發規格 7.26 順序 2）
- **背景**：順序 1 已合併（PR #95）。architect review 建議（不阻擋、交給本單）：測試 Kafka 的 `CLUSTER_ID` 目前與 `.env.example` 開發環境相同；改成不同值，session 重置前以 `AdminClient.list_topics().cluster_id` 比對，避免有人把 `IT_KAFKA_BOOTSTRAP` 指到開發 Kafka（`localhost:9092`）時刪掉開發 topic
- **設計依據**：`docs/development-spec.md` 7.26（做法 13、15、平行執行的隔離、用法、風險、派工順序 2）；D-015
- **相依**：test-infra-compose（已合併）
- **負責檔案**：
  - `tests/integration/**`（含 `conftest.py`；去掉固定等待：`streaming/test_heat_app.py`、`common/test_producer_partition.py`；平行隔離：fixture、slot 名稱、`xdist_group` 標記）
  - `tests/helpers/clickhouse.py`、`pyproject.toml`、`uv.lock`（加 pytest-xdist）
  - `Makefile`（`coverage` 加 `-n auto --dist loadgroup`）、`compose.yaml`（`test` 的預設 command、測試 Kafka 的 `CLUSTER_ID`）
  - `docs/development-spec.md`（7.26 補實測、cluster_id 防呆寫進做法 8 與威脅表，本節標完成）
- **禁區**：不改 `src/`、`.github/workflows/ci.yml`、`compose.ci.yaml`、`.env.example`；不掛 docker socket；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] `docker compose --env-file .env -f .worktrees/test-infra-fast-waits/compose.yaml run --rm test` 連跑兩次都全過；再以 `pytest tests/integration -n 0` 跑一次也全過，附輸出
  - [ ] PR 的 CI：改程式的 PR Integration Test job ≤ 3 分鐘；附 run 連結與 `--durations=15` 輸出（只改文件 ≤ 1 分鐘由 7.26 做法 12 保證，回報附依據）
  - [ ] Kafka 重置前比對 `cluster_id`，不符就拒絕、不刪任何東西；有單元或整合測試證明
  - [ ] 開發環境（專案 `radar`）的容器與資料不受影響；`make check` 通過；交單前 `down -v`
- **驗證指令**：`make check`；`docker compose --env-file .env -f .worktrees/test-infra-fast-waits/compose.yaml run --rm test`
- **回報檔**：`reports/test-infra-fast-waits.json`

## 執行資訊（task.py 產生）

- Issue：#96
- 分支：`chore/test-infra-fast-waits`（從 develop 開出）
- 工作目錄：`.worktrees/test-infra-fast-waits`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-20

範圍更正（manager 寫錯格式：`tests/integration/**` 不被範圍檢查接受，應為目錄前綴）。負責檔案以下列為準，內容與原意相同：
  - `tests/integration/`
  - `tests/helpers/clickhouse.py`、`pyproject.toml`、`uv.lock`、`Makefile`、`compose.yaml`、`docs/development-spec.md`
另：驗收條件要 CI 的 `--durations=15` 輸出，`Makefile` 在負責檔案內，請在 `coverage` 目標加上 `--durations=15`（CI 走 `make coverage`，不需改 ci.yml）。改完 commit、更新回報。

## 追加 2026-10-20

範圍更正補欄位標題（上一則漏寫，程式讀不到）；內容同上一則，不需 worker 動作：

- **負責檔案**：
  - `tests/integration/`
  - `tests/helpers/clickhouse.py`
  - `pyproject.toml`
  - `uv.lock`
  - `Makefile`
  - `compose.yaml`
  - `docs/development-spec.md`
