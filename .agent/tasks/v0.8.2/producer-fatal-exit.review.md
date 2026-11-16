APPROVE c06e86b

## 檢查範圍

- `gh pr diff 298`（7 檔），對照派工單 `.agent/tasks/producer-fatal-exit.md`、`docs/development-spec.md` 7.30 A、D-042、qa 結果（PASS c06e86b）、仲裁（TEST_WRONG 69b2584）
- CI（headRefOid c06e86b）：Check、Integration Test、Security 皆 pass

## 逐項

| 項目 | 結果 |
|---|---|
| 負責檔案 | 改動都在負責檔案內；驗收測試只有 b45a160（qa lock）與 c06e86b（依仲裁改 `wired` fixture 與 `test_api_fatal_logs_critical`，改法與 ruling 一致）；未動其他服務入口、未動文件 |
| `producer.py` 偵測三入口 | produce 的 `KafkaException` 且 `fatal()`、`_on_delivery` fatal、`error_cb`（只處理 fatal、非 fatal 不記 log）都進 `_set_fatal`，只留第一個；`ProducerFatalError(Exception)` 帶 `error`，不繼承 `KafkaException`／`DeliveryError`；符合 7.30 A「偵測」「例外」 |
| `send`／`flush` | 已 fatal 時 `send` 先丟、不呼叫 librdkafka；`flush` 前後各檢查一次，fatal 優先於 `TimeoutError`／`DeliveryError`；非 fatal 路徑（BufferError 重試、DeliveryError、TimeoutError）不變；符合 7.30 A「flush()」 |
| scheduler | `_logged(fn, on_fatal)` 可帶參數並包住列表任務 sender、`sync_boards`、`due_posts`、`lock`；`on_fatal` 記 CRITICAL、`shutdown(wait=False)`；`finally` 先 `lock.release()`，`finally` 的 `producer.flush()` 在 fatal 時再丟一次（7.30 A 明文接受），`main()` 的 `@log.catch(level="CRITICAL")` 保留；符合 7.30 A「scheduler」「結束方式」 |
| API | `create_app` 註冊 handler：`log.critical`、503、body `{"detail": "kafka unavailable"}`，`BackgroundTask(exit_for_restart)` 先 `log.close()` 再 `os._exit(70)`；符合 7.30 A「API」 |
| consumer 類 | 依 7.30 A 不改；驗收測試涵蓋 handler／DLQ fatal 不 commit 並中止 |
| 寫死設定、安全 | 無新設定值；503 回應不帶內部錯誤細節；`RESTART_EXIT_CODE` 是程式常數非部署設定 |
| 測試是否測到驗收條件 | 驗收測試 37 個涵蓋條件 1–4（三入口、非 KafkaException、flush 立即丟、非 fatal 不變、scheduler 列表任務／due_posts 經 main 丟出且有 CRITICAL、lock 先釋放、consumer 不 commit、API 503＋exit 順序）；單元測試補 `_logged`、`exit_for_restart`、produce fatal |
| 覆蓋率 | CI coverage gate 通過 |

## 非阻擋備註

- `scheduler.main()` fatal 時 `finally` 的 `producer.flush()` 先丟，`boards.close()`、`engine.dispose()` 不會執行、`raise fatal[0]` 也到不了；程序隨即結束，7.30 A 已接受此行為，不需改
- `error_cb` 只在未注入 producer 時掛上（注入的 fake 不經 `producer_config`）；驗收測試以 monkeypatch `Producer` 驗證，足夠
