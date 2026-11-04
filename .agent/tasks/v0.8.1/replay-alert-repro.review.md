APPROVE acc1ee6

# replay-alert-repro code review（PR #265，對 develop 93342b3）

## 檢查範圍

- `gh pr view 265`：headRefOid acc1ee69，與 worktree HEAD 一致；merge-base = develop 93342b3
- 完整 diff（`git diff develop...HEAD`）：`docs/development-spec.md`（只動 7.20）、`src/radar/streaming/replay.py`、`tests/unit/streaming/test_replay.py`、驗收測試 2 檔；全部在派工單負責檔案內
- 驗收測試目錄只被 qa 的 `test(replay-alert-repro)` commit（206aa1f、c5ee372）改過，worker 沒碰
- 本機重跑（worktree）：`uv run pytest tests/unit/acceptance/replay-alert-repro tests/unit/streaming -q` → `151 passed`；`uv run ruff check src tests` → All checks passed；`grep -rn "TODO(replay-alert-repro)" src tests` → 無結果；`surge --help` 每個參數都有說明

## 重點確認

| 項目 | 結果 | 依據 |
|---|---|---|
| 正式 heat 行為沒被改到 | 通過 | `src/radar/streaming/heat.py`、`radar.common.settings.HeatSettings` 不在 diff；replay.py 仍只寫 `names.REPLAY_COMMENTS`；新加的 `warn_if_replay_topic_dirty` 只讀 watermark（consumer 不 subscribe、不 commit），不碰正式 topic、alerts、bot、compose |
| 7.20 步驟與程式一致 | 通過 | 參數名、預設值與 `build_parser()` 一致（`--speed` 預設 1、`--count` 預設 `HEAT_POST_MIN_COUNT`、`--minutes` 3）；文中數值與 heat 一致：`warmup_min=60`、`max_delay_min=30`、`grace_min=2`、`min_count=30`（看板）、`post_min_count=80`、`cooldown_min=30`；「watermark 之前超過寬限就丟」對應 `heat.py` 的 `minute < state.watermark - config.grace_min`；新 group 從開頭讀對應 `auto_offset_reset="earliest"`；`heat consuming … as …` 與 heat.py 的 log 字串相同；`make topics` 執行 `tools/create_topics.py`；舊訊息警告只在 `replay` 前檢查，與步驟 1 的說明一致（acc1ee6） |
| 錯誤處理與其他 CLI 一致 | 通過 | 用 `radar.common.cli.fail`（`error: …`、exit 1，與 `evaluate`、`import_model` 的 `sys.exit("error: …")` 同格式）；參數型別錯用 `argparse.ArgumentTypeError`／`parser.error`（exit 2，manager 已裁定 usage 區塊不算問題）；缺 `KAFKA_BOOTSTRAP_SERVERS` 列變數名與 `ENV_FILE_HINT`，同 `load_settings`；`@log.catch` 不吞 `SystemExit`，結束碼正確 |
| 驗收條件有被測到 | 通過 | `--help`、各種輸入錯誤（含 subprocess 無 traceback、輸入錯不連 Kafka）、7.20 五項內容、surge 不誤報／replay 前有殘留仍警告，都有驗收測試；單元測試涵蓋 `parse_time`、`positive_*`、`post_id_arg`、`replay_topic_has_messages`、`warn_if_replay_topic_dirty`（Kafka 錯誤時仍 close） |
| 寫死設定 | 無 | 7.20 的 localhost 位址與 `.env.example` 相同，只是說明；程式沒有新寫死值 |

## 非阻擋建議（不影響本次合併，可開 issue 再做）

1. `src/radar/streaming/replay.py:328` `kafka_settings_or_fail` 與 `radar.common.cli.load_settings` 重複；可改成 `load_settings(KafkaSettings)`（會繞過 `get_kafka_settings` 的 lru_cache，對一次性 CLI 沒有影響）
2. `src/radar/streaming/replay.py` `--start-floor` 仍是 `type=int`，負數不擋；7.20 沒列為常見錯誤，不算偏離
3. `record --out` 寫不進去（權限、路徑是目錄）的 `OSError` 仍會走 `@log.catch` 印 traceback；不在 7.20 列的常見錯誤內，不算偏離
