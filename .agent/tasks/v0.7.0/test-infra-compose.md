# 派工單 test-infra-compose

- **類型**：chore
- **負責**：backend
- **目標**：整合測試改用根目錄 `compose.yaml` 的 `test` 服務與 kafka／postgres／clickhouse，移除 testcontainers；CI 每個事件只跑一次整合測試、只改文件時跳過（開發規格 7.26 順序 1）
- **背景**：設計已核可（PR #87）。dashboard 的 `infra/clickhouse/users.d/grafana.xml`（`from_env` 讀密碼）還沒進 develop；若本單合併前它先進了，測試用 ClickHouse 要提供對應變數（7.26 風險表 users.d 列），否則由 dashboard-grafana-infra 補
- **設計依據**：`docs/development-spec.md` 7.26（做法 1～14、用法、風險、派工順序）；D-011、D-015（xdist 在下一張單 test-infra-fast-waits，本單不加）
- **相依**：無
- **負責檔案**：
  - `compose.yaml`、`compose.ci.yaml`
  - `tests/integration/**`（fixture、重置；`streaming/test_heat_app.py`、`common/test_producer_partition.py` 只改 fixture）
  - `tests/helpers/clickhouse.py`、`pyproject.toml`、`uv.lock`、`.env.example`、`Makefile`、`.github/workflows/ci.yml`
  - `docs/development-spec.md`（1.1、1.3、5 章改成新做法，7.26 標完成）
- **禁區**：不加 pytest-xdist、不去掉固定等待（下一張單）；不掛 docker socket；不改 `src/`；不改 `CLAUDE.md`（文字需改處寫在回報，manager 轉甲方）
- **驗收測試**：
  - `tests/unit/acceptance/test_infra/`
- **驗收條件**：
  - [ ] `tests/unit/acceptance/test_infra/` 全過，`make check` 通過
  - [ ] `docker compose --env-file .env -f .worktrees/test-infra-compose/compose.yaml run --rm test` 跑全部整合測試（約 135 個）全過，附輸出
  - [ ] PR 的 CI：Integration Test 只跑一次整合測試且含覆蓋率閘門；Check 只跑 `make check`；開發環境（專案 `radar`）的容器與資料不受影響
  - [ ] 回報列出 `CLAUDE.md` 需改的文字（testcontainers、docker 指令說明）
- **驗證指令**：`make check`；`docker compose --env-file .env -f .worktrees/test-infra-compose/compose.yaml run --rm test`
- **回報檔**：`reports/test-infra-compose.json`

## 執行資訊（task.py 產生）

- Issue：#90
- 分支：`chore/test-infra-compose`（從 develop 開出）
- 工作目錄：`.worktrees/test-infra-compose`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-20

範圍更正（manager 寫錯格式：`tests/integration/**` 不被範圍檢查接受，應為目錄前綴）。負責檔案以下列為準，內容與原意相同，另補 qa 建的上層套件檔：

- **負責檔案**：
  - `compose.yaml`
  - `compose.ci.yaml`
  - `tests/integration/`
  - `tests/helpers/clickhouse.py`
  - `pyproject.toml`
  - `uv.lock`
  - `.env.example`
  - `Makefile`
  - `.github/workflows/ci.yml`
  - `docs/development-spec.md`
  - `tests/unit/acceptance/__init__.py`

## 追加 2026-10-20

### reports/test-infra-compose.review.md

REQUEST_CHANGES efe6826

# Review PR #95 test-infra-compose（commit efe6826）

對照：派工單 `tasks/test-infra-compose.md`（含 2026-10-20 範圍更正）、開發規格 7.26、backend-standards 第 6 節、qa 證據 `reports/test-infra-compose.qa.md`。

## 必修（2 條，都是文件同步，程式不用改）

1. `docs/development-spec.md:1210`（7.26 風險表 users.d 一列）— 仍寫「測試的 ClickHouse 掛整個 `users.d` 時缺環境變數會啟動失敗…後合併的一方補」，與本 PR 改過的做法 7（第 1150 行：只單檔掛 `named_collections.xml`、`radar.xml`，`grafana.xml` 不會被載入）矛盾；7.25 第 1076 行也引用這一列，`dashboard-grafana-infra` 會照錯的前提做 — 改成：「compose 的 `clickhouse` 只單檔掛載（做法 7），`grafana.xml` 不會自動載入；`dashboard-grafana-infra` 要在 `compose.yaml` 的 `clickhouse` 加一條單檔唯讀掛 `users.d/grafana.xml`，並在 compose 內寫明 `CLICKHOUSE_GRAFANA_*` 的測試值（不讀 `.env`）」。
2. `docs/development-spec.md:1180` — 「每套估 1.5～2 GB，`test-infra-compose` 實測後回寫」已過時，實測值在第 1182 行（尖峰約 1.4 GiB，以 1.5 GB 計） — 改成「每套約 1.5 GB（實測見下方實作補充）」，同一件事只寫一次。

## 檢查結果

| 項目 | 結論 | 依據 |
|---|---|---|
| `compose.yaml` 做法 1、3～6 | 符合 | 無 `name`／`container_name`／對外 port；`test` 唯讀掛 `.`、venv 與快取用 named volume；不掛 docker socket、不 privileged、不用 host network；版本 `${KEY:?}`；tmpfs；Kafka alias `kafka_1～3`、`:29092`、rebalance delay 0、heap 512m；`.env` 只用來代換版本，容器拿不到機密 |
| 做法 7 偏離（ClickHouse 單檔掛載） | 合理，接受 | `infra/clickhouse/config.d`、`users.d` 目前各只有一個檔，單檔掛載內容等價；整目錄唯讀覆蓋會蓋掉 image 自帶的 `config.d`（listen 設定）且讓 entrypoint 寫不進 `users.d` 的預設使用者檔；與 `infra/docker-compose.yaml:341-342` 的開發環境寫法一致；已回寫 7.26 第 1150 行。唯一後果是 grafana 帳號要另加掛載，見必修 1 |
| `compose.ci.yaml` 做法 10 | 符合 | 三個 port 只綁 `127.0.0.1:${IT_*_HOST_PORT:?}`；Kafka 加 EXTERNAL listener 廣播 `127.0.0.1` |
| `ci.yml` 做法 10～12 | 符合 | Check 只剩 `make check`；Integration Test：變更偵測（PR 比 base、push 比 before、比不到當有改）→ registry-mirrors → pull → `up -d --wait` → runner 上 `make coverage` → 閘門只在 PR→develop；不用 `paths-ignore`；無 `TESTCONTAINERS_*` |
| CI 實跑（run 39394150949） | 通過 | Integration Test log：`1201 passed in 342.09s`（單元 1066＋整合 135，只跑一次）、`coverage_gate.py` 有執行；Check 42s。文件跳過分支未被實跑，靜態檢視邏輯正確（regex `^(docs/\|tasks/\|reports/)\|^[^/]+\.md$`） |
| conftest 重置（做法 2、8） | 符合 | 缺 `IT_*` 即 `pytest.exit`（不 skip）；PG 先 `current_database()=='radar_it'` 才 DROP；ClickHouse `assert_test_clickhouse`（主機允許清單＋db=`radar`）在任何 DROP 前；Kafka 每個 bootstrap 主機檢查後才建 AdminClient；順序 PG→CH drop→Kafka→CH migration 與 7.26 實作補充一致；`test_reset_guard` 驗到拒絕時不送 DROP／CREATE |
| 做法 9 | 符合 | `test_clickhouse_migrations` 另建 DB 套完即 `drop_queue_tables` |
| 派工單範圍 | 符合 | 變更檔全在更正後的負責檔案內；未改 `src/`、`CLAUDE.md`；未加 xdist、未去固定等待；`test_producer_partition.py` 未動、`test_heat_app.py` 只改 fixture |
| 寫死設定 | 無問題 | 測試帳密 `radar`/`it` 為測試專用固定值，設計 7.25 第 1076 行同意寫在 compose；port 走 `IT_*_HOST_PORT` |
| testcontainers 移除 | 完成 | `pyproject.toml`、`uv.lock` 已移除；殘留只剩 `CLAUDE.md:86`（禁區，已列在回報 open_questions 給 manager） |
| 文件同步 1.1、1.3、5 章 | 已改 | 第 39、104、301 行；7.26 狀態列已更新；剩必修 1、2 |
| 本機驗證（我在 worktree 執行） | 通過 | `PYTHONPATH=src uv run --no-sync pytest tests/unit -q` → `1066 passed in 3.65s`；`ruff check .` → `All checks passed!`；docker 實跑未重做（以 worker 回報 135 passed 與 CI 為據） |

## 建議（不阻擋，可交給 `test-infra-fast-waits`，它也負責 conftest）

- 主機允許清單含 `localhost`／`127.0.0.1`（CI 需要），而開發環境 Kafka 在 `localhost:9092` 無認證：有人手動設 `IT_KAFKA_BOOTSTRAP=localhost:9092` 且 PG 指向測試服務時，session 重置會刪掉開發環境的 topic（PG／ClickHouse 因帳密 `it` 不符會先失敗，Kafka 沒有這層）。另外 `compose.yaml` 的 `CLUSTER_ID` 與 `.env.example` 開發環境相同。可改成測試 Kafka 用不同的 `CLUSTER_ID`，重置前以 `AdminClient.list_topics().cluster_id` 比對，比主機名更可靠。
- 分支落後 develop 一個 docs commit（722cc40），合併前由流程腳本處理即可。
