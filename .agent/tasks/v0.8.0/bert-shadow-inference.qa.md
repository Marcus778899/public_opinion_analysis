PASS a8f1d2c

# 驗證證據 bert-shadow-inference（PR #165）

## 驗收條件對照
- shadow 只寫 `predictions.shadow`、`predictions_shadow` 有資料而 `predictions` 沒有：acceptance `test_shadow_role_writes_only_shadow_topic`、`test_shadow_prediction_lands_in_predictions_shadow_and_not_in_predictions` 通過；main.py 以 `ROLE_TARGETS[settings.role]` 查表取 topic，無寫死
- group `inference-shadow-<model_version>`：`test_shadow_role_commits_under_group_per_model_version` 通過；main.py 用 `consumer_group(role, version)`（來自 roles.py）
- 重啟從 `predictions_shadow` 載入快取：`test_shadow_restart_loads_hash_cache_from_predictions_shadow_only`、`..._does_not_repredict_unchanged_post`、`test_load_cache_shadow_table_ignores_primary_rows` 通過
- primary 不變：`test_primary_role_still_writes_only_primary_topic`、`test_primary_restart_still_loads_cache_from_predictions`、`test_load_cache_default_table_ignores_shadow_rows` 通過
- 冪等與 DLQ：`test_shadow_duplicate_create_event_produces_one_prediction`、`test_shadow_undecodable_message_lands_in_dlq_...`，另 `test_inference_consumer.py` 既有 DLQ 測試通過
- `CLICKHOUSE_TOPICS` 含 `names.PREDICTIONS_SHADOW`：conftest diff 確認，`test_clickhouse_topics_include_predictions_shadow` 通過
- `grep -rn "TODO(bert-shadow-inference)" src tests`：無結果；`require_primary` 在 src/tests/docs 無殘留
- 禁區（roles.py、settings.py、classifier.py、test_roles.py）：`git diff develop...HEAD --stat` 無改動

## 驗收測試未被改動
`git diff --stat 0f4b100 HEAD -- tests/integration/acceptance/bert-shadow-inference/` 輸出為空（lock 0f4b100 之後無變動）。

## 7.27 同步
`git diff develop...HEAD -- docs/development-spec.md` 只改 7.27 一行：移除 `require_primary` 描述，改為依角色查表、shadow 寫 `predictions.shadow`、從 `predictions_shadow` 載入、`load_cache` 的 `table` 參數只接受對照表內表名、`classifier.top_class`；與 main.py 一致，未動 D-025 相關句。

## 指令與輸出（自行執行）
- `uv run ruff check .` → All checks passed!；`uv run ruff format --check .` → 280 files already formatted
- `uv run pytest tests/unit -q -n 4` → `1286 passed in 4.77s`
- `docker compose ls`（跑前）→ 無其他堆疊
- `docker compose --env-file .env -f .worktrees/bert-shadow-inference/compose.yaml run --rm test` → `344 passed in 60.02s`（含 acceptance/bert-shadow-inference 全部 11 項）
- `... down -v` → 容器、volume、network 全部 Removed
- 寫死設定值搜尋（localhost、127.0.0.1、port）於 main.py 與新測試：無

## 備註（非 FAIL）
- `make check` 的 pre-commit 在 sandbox 未直接跑，以 ruff check/format + 單元測試代替
- 負責檔案列的 `test_inference_cache.py` 未修改（無需要）
- CI 全綠由 merge 流程檢查，不列入判定
