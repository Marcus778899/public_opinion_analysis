PASS bccac84

## 驗證證據（worktree .worktrees/bert-classifier，HEAD bccac84）

| 項目 | 結果 |
|---|---|
| 驗收測試未被改 | `git diff 755e0f0 HEAD --stat -- tests/unit/acceptance tests/helpers` 無輸出（lock commit 後沒改動） |
| 驗收＋ml 測試 | `uv run pytest tests/unit/acceptance/bert-classifier tests/unit/ml -q` -> `302 passed` |
| 全部單元測試 | `uv run pytest tests/unit -q -x` -> `1257 passed` |
| lint | `uv run ruff check .` -> All checks passed!；`ruff format --check .` -> 274 files already formatted |
| TODO 殘留 | `grep -rn "TODO(bert-classifier)" src tests` 只命中驗收測試自己的檢查字串（test_classifier_acceptance.py:289） |
| 驗收條件 1-3 | 由驗收測試涵蓋（三類齊全／總和為 1、缺類補 0、threads、fp32／int8、舊卡片、runtime 欄位），全數通過 |

## review 要求逐項

- 分批大小依 batch_size：`_predict_in_batches` 以 `range(0, len, batch_size)` 切批；單元測試 `test_evaluate_model_predicts_in_batches_of_batch_size` 驗證 36 篇、batch_size=10 呼叫為 [10,10,10,6]；`evaluate_by_board` 透過 `evaluate_model` 傳入 batch_size（測試每次呼叫 <= 7）；batch_size<1 拒絕（測試通過）。已通過。
- `main()` 傳入：evaluate.py:301-302 `batch_size=settings.batch_size`，`settings = InferenceSettings`，其 `batch_size` 預設 100（settings.py:95）對應 `INFERENCE_BATCH_SIZE`，與 `DEFAULT_BATCH_SIZE = 100` 一致；`measure_runtime` 同用 settings.batch_size／threads。已通過。
- 7.27 同步：development-spec.md 7.27「載入」該行已補「評估也依 `INFERENCE_BATCH_SIZE` 分批推論（keyword-only `batch_size`，預設 100），記憶體峰值才對應 shadow 的設定」，與程式一致；只動 7.27。已通過。
- 寫死設定：threads、batch_size 皆讀 InferenceSettings，預設值 100 是與 settings 對齊的常數，不算新增外部設定。

## 未實際驗證（不影響判定）

- `evaluate.main()` 需 ClickHouse 與 .env，sandbox 內未啟動執行；其傳參由原始碼閱讀與單元測試確認。
- 不擋合併的建議（evaluate_by_board 重複推論、sklearn 也印 INFERENCE_THREADS）review 已列為非必要，不判 FAIL。

問題數量：0
