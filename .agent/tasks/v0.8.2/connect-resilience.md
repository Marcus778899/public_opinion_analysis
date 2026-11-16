# 派工單 connect-resilience

- **類型**：fix
- **負責**：backend
- **目標**：Connect 內部 topic 新環境設 2 份副本、健康檢查確認 connector 存在、cdc-watchdog 持續 404 告警（#282）；init 遇 task FAILED 先重啟（#262）
- **背景**：
  - #282：內部 topic RF=1，一台 broker 卡住 connect 就起不來、REST 活著但 connector 404（`.agent/reports/dev-stall-recover.json`）；甲方決定 2 份副本（D-041）。既有環境的 reassignment 是另一張操作單，這張不碰開發環境
  - #262：重建 postgres 後 Debezium task FAILED，init 以 CRITICAL 結束（`docs/uat/v0.8.1.md` F-4）
  - 7.30「需調查」第 1 項由這張查：Connect 建內部 topic 是否套用 `CONNECT_*_STORAGE_MIN_INSYNC_REPLICAS`，查不到就照 7.30 拿掉那三個變數並在回報說明
- **設計依據**：`docs/development-spec.md` 7.30 B、D 與派工順序第 2 列；D-041、D-042
- **相依**：無
- **負責檔案**：
  - `infra/docker-compose.yaml`（只限 `connect`、`init`）
  - `src/radar/common/kafka/connect.py`
  - `tools/register_connector.py`
  - `src/radar/cdc/watchdog.py`
  - `src/radar/common/settings.py`（只限 `CdcWatchdogSettings`）
  - `.env.example`（選填註解 `# CDC_WATCHDOG_CONNECTOR_MISSING_ALERT_S=300`）
  - `tests/unit/common/kafka/test_connect.py`
  - `tests/unit/cdc/test_watchdog.py`
  - `tests/unit/common/test_settings.py`
- **禁區**：不改文件（與 7.30 不符時回報 manager）；不動開發環境的 Kafka、connect 與資料
- **驗收測試**：
  - `tests/unit/acceptance/connect-resilience/`
  - `tests/unit/acceptance/infra-secret-guard/test_compose_secret_guard.py`（只限 `test_guard_init_depends_on_unchanged`：connect 改 `service_started`）
  - `tests/unit/acceptance/init-exit-code/test_init_exit_code_acceptance.py`（只限 `test_connector_task_failed_exits_nonzero_and_logs_step_and_reason`：改為斷言先送過重啟才失敗）
- **驗收條件**：
  - [ ] compose：三個內部 topic RF=2、min.isr=1；healthcheck 含 `/health` 與 `/connectors/radar-cdc`、有 `start_period`；`init` 對 connect 為 `service_started`
  - [ ] `wait_until_ready` 打 `/health`；task FAILED 後重啟一次就 RUNNING 時成功，重啟次數用完仍 FAILED 時失敗且有送重啟
  - [ ] watchdog：404 在門檻前只記一次 WARNING、超過門檻記 ERROR 並讓 heartbeat 送 `/fail`，只在狀態改變時記
  - [ ] `make check` 通過、改到的程式碼覆蓋率達門檻
- **驗證指令**：`make check`；`uv run pytest tests/unit/acceptance/connect-resilience tests/unit/acceptance/infra-secret-guard tests/unit/acceptance/init-exit-code -v`
- **回報檔**：`.agent/reports/connect-resilience.json`

## 執行資訊（ae task 產生）

- Issue：#294
- 分支：`fix/connect-resilience`（從 develop 開出）
- 工作目錄：`.worktrees/connect-resilience`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`

## 追加 2026-11-04

### .agent/reports/connect-resilience.review.md

REQUEST_CHANGES a00da90

## 檢查範圍

- `gh pr diff 296`（14 檔），對照派工單 `.agent/tasks/connect-resilience.md`、開發規格 7.30 B、D、自行決定、需調查 1、qa 結果 `.agent/reports/connect-resilience.qa.md`、worker 回報 `.agent/reports/connect-resilience.json`
- 負責檔案：worker commit a00da90 只改了負責檔案；驗收測試三個檔（含兩個既有測試的指定函式）由 qa commit 5ba320c 改，worker 沒碰
- 寫死設定：`register_connector` 的 `TASK_RESTART_LIMIT`／`TASK_RESTART_GRACE_S` 是 7.30 D 指定的模組常數；新設定 `CDC_WATCHDOG_CONNECTOR_MISSING_ALERT_S` 已加進 `.env.example` 的選填註解；沒有寫死的 port／URL
- CI：Check、Integration Test、Security 都 pass

## 符合設計、沒有問題的部分

| 項目 | 結果 |
|---|---|
| healthcheck `/health && /connectors/radar-cdc`、`start_period: 300s`；`init` 對 connect `service_started` | 符合 7.30 B |
| `wait_until_ready` 改打 `/health`，逾時訊息不變 | 符合 |
| `wait_until_running` keyword-only `restart_limit=0`／`restart_grace_s=15.0`；預設 0 時行為與原本一樣；grace 內的 FAILED 不判定；重啟請求失敗往上丟；總時間受 `timeout_s` 限制；limit 2、grace 15、poll 2 約 32 秒失敗 | 符合 7.30 D |
| watchdog `MissingWatch`：404 第一次 WARNING、超過門檻（嚴格大於）一次 ERROR（提示文字同 7.30 B）、告警後恢復 INFO、Connect 連不上／5xx 不改變狀態、`is_cdc_healthy` 告警時回 False 讓 heartbeat 送 `/fail`；`main()` 有建立並傳入 | 符合 7.30 B |
| `CdcWatchdogSettings.connector_missing_alert_s = 300.0` | 符合 |
| 驗收測試有測到驗收條件：重啟一次後 RUNNING 成功、次數用完仍 FAILED 失敗且有送重啟（`RESTART_SENT`）、404 門檻前後與只記一次、heartbeat `/fail` | 是 |

## 要修改

1. `infra/docker-compose.yaml:350-352` — 拿掉三個 `CONNECT_*_STORAGE_MIN_INSYNC_REPLICAS` 的前提「查不到」不成立：Kafka Connect 會把 `config.storage.`／`offset.storage.`／`status.storage.` 前綴的 topic 設定套用到它自己建的內部 topic（KIP-605，2.6 起）。原始碼（apache/kafka 4.1.x）：`DistributedConfig.topicSettings(prefix)` 回傳 `originalsWithPrefix(prefix)`，只拿掉 `topic`、`replication.factor`、`partitions`、`cleanup.policy`；`KafkaOffsetBackingStore` 在 `TopicAdmin.defineTopic(topic).config(offsetStorageTopicSettings())` 用它，`KafkaConfigBackingStore`（`configStorageTopicSettings()`）、`KafkaStatusBackingStore`（`statusStorageTopicSettings()`）也一樣。worker 只查了 context7 的文件，沒有查 7.30 需調查 1 指定的 `DistributedConfig` 原始碼。現在的寫法讓新環境內部 topic RF=2、min.isr=broker 預設 2，任一台 broker 停掉時約 2/3 的 partition 寫不進去，達不到 7.30 B 的目的，也不符合派工單驗收條件「三個內部 topic RF=2、min.isr=1」。 — 要怎麼改：在三個 `*_REPLICATION_FACTOR` 之後加上 `CONNECT_CONFIG_STORAGE_MIN_INSYNC_REPLICAS: '1'`、`CONNECT_OFFSET_STORAGE_MIN_INSYNC_REPLICAS: '1'`、`CONNECT_STATUS_STORAGE_MIN_INSYNC_REPLICAS: '1'`（entrypoint 會轉成 `config.storage.min.insync.replicas` 等，7.30 B 已確認），註解改成同時說明 RF 與 min.isr；回報裡的「需調查 1 查不到、新環境維持 broker 預設 2、要補已知限制」改成「已由原始碼確認會套用」並附上面的出處。驗收測試 `test_internal_topic_min_insync_replicas_is_1_when_set` 接受三個都有且值為 `'1'`，不用改測試

## 不算問題的備註

- 告警前（只記過 WARNING）就恢復時不記 INFO：7.30 B 沒寫清楚；驗收測試定為「告警後找到」才算 RECOVERED，照它即可
- compose healthcheck 與 init 流程沒有實機跑過，由 `stability-dev-verify` 演練；`e2e-up` 的等待條件改變，7.30 已寫明發版前請甲方跑一次 `make e2e`
