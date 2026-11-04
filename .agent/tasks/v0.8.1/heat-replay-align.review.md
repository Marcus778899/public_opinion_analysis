APPROVE 8a8406a

# Review PR #258 heat-replay-align（diff：develop...8a8406a，11 檔）

## 檢查項目

| 項目 | 結果 |
|---|---|
| 負責檔案 | 改到的 11 檔都在派工單（含追加）清單內；驗收測試只有 d5c3e90（qa 的 `test(heat-replay-align)`）新增，之後 `git diff d5c3e90 HEAD -- tests/unit/acceptance` 沒有變動 |
| 禁區 | `heat.py` 只移除 `names` import、`build_app` 改用 `settings.output_topic`；門檻、偵測邏輯（`advance`／`close_minute`／`evaluate`）沒動；`HeatSettings.output_topic` 預設 `"alerts"` 與原 `names.ALERTS` 相同；bot、compose 沒動 |
| 追加的介面 | `HeatSettings.output_topic`／`HEAT_OUTPUT_TOPIC`、`names.REPLAY_ALERTS="replay.alerts"`、7.20 用 `HEAT_CONSUMER_GROUP=heat-replay-$(date +%s)` 與 `HEAT_OUTPUT_TOPIC=replay.alerts`，都照做 |
| 驗收 1（不推 Telegram） | bot 只訂閱 `names.ALERTS`（`src/radar/bot/main.py`）；另確認 ClickHouse 的 `alerts_queue` 只讀 `kafka_topic_list='alerts'`（`infra/clickhouse/migrations/0002_json_topics.sql:62`），回放警示也不會再灌進「看板概況」的警示數（UAT 的附帶影響一併解掉） |
| 驗收 2（surge 則數與尾事件） | `--count` 預設 `None`，執行時取 `HeatSettings().post_min_count`，沒寫死。逐步推演：`surge_events` 最後一則在 `now`（`start + step*count`，微秒捨入只會更早），`surge_tail_event` 在 `now+1 分`，`event_minute` 用 `__source_ts_ms`，必定落在下一分鐘 → `advance` 結算 `range(watermark, minute)` 包含 `floor(now)`，此時 10 分鐘視窗包含全部 count 則，文章值 ≥ `post_min_count`；`is_fresh` 延遲 0 不丟棄。尾事件 floor = `start_floor + count`，不與暴增本身重複 |
| 驗收 3（新 consumer group） | 7.20 寫法與 `.env.example` 註解、`HeatSettings` 欄位名一致；Quix 的 state 目錄依 consumer group 分開，新 group 不會讀到舊 state |
| 文件同步 | 開發規格 7.20 已更新；`topics.yaml` 加 `replay.alerts`（24 小時），`create_topics` 讀 topics.yaml 會建 |
| 設定與安全 | 沒有寫死值；新設定依 D-009 以註解寫進 `.env.example`；沒有安全疑慮（只是換輸出 topic 名稱，來源是運維設定的環境變數） |
| 測試 | 驗收測試真的跑 `replay.main()` 與 `heat.build_app`（mock Kafka／Apicurio），驗到預設則數跟著 `HEAT_POST_MIN_COUNT`、尾事件單獨落在下一分鐘、預設輸出仍是 `alerts`；單元測試補了 `surge_tail_event`、`build_app` 輸出 topic、`HeatSettings` 預設值 |

## 實際執行（worktree，HEAD 8a8406a）

- `PYTHONPATH=<worktree>/src uv run --no-sync pytest tests/unit/acceptance/heat-replay-align tests/unit/streaming tests/unit/common -q` → 358 passed
- `uv run --no-sync ruff check src tests` → All checks passed!；`ruff format --check .` → 325 files already formatted
- `grep -rn "TODO(heat-replay-align)" src tests tools` → 無結果

## 不擋合併的備註

1. `src/radar/streaming/heat.py:408` 的 `build_app` docstring 還寫「輸出到 alerts」（qa 也提到）；模組 docstring 第 1 行「寫入 alerts」在預設下仍正確。下次碰 heat.py 時順手改成「輸出到 `settings.output_topic`」。
2. 尾事件結算沒有做端到端實跑：上面已逐步推演 `heat.py` 的結算邏輯，結論成立；建議甲方下次回放驗收時實測確認。
3. 開發規格 5 階段驗收表（`docs/development-spec.md:563`）的「人工暴增 2 分鐘內收到 Telegram 通知」當時是靠回放推到正式 alerts 驗的。照新的 7.20 步驟不會推到 Telegram，日後要重驗這一條，得刻意設 `HEAT_OUTPUT_TOPIC=alerts`。這是歷史紀錄，不用改；給 manager 參考。
4. 每次回放都用新的 consumer group，Kafka 上會多出一組 Quix 內部 topic（`repartition__heat-replay-<ts>…`、`changelog__…`），`HEAT_STATE_DIR` 底下也會多一個目錄，都不會自動清掉。量很小，可以考慮在 7.20 補一行回放完的清理方式（另開單，不屬於這張）。
5. 既有環境要先 `make topics` 才會有 `replay.alerts`；容器內跑回放要用 compose 覆寫檔。兩項都已列在 worker 的 open_questions。
