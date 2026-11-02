APPROVE bccac84

## 檢查範圍

這是 PR #161 的第二輪 review，審整個 PR，不只看這輪改的地方。依據：`gh pr diff 161`、派工單 `tasks/bert-classifier.md`（含 2026-10-22 的兩次追加）、開發規格 7.27「載入」「模型包格式」「測試」「檔案分工」、CLAUDE.md 程式碼規範。

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改了 classifier.py、evaluate.py、兩個單元測試、`docs/development-spec.md`（只動 7.27「載入」）。`tests/unit/acceptance`、`tests/helpers` 只被 qa 的 `755e0f0 test(bert-classifier)` 改過。`inference/main.py`、`fakes.py`、`settings.py` 都沒改 |
| 跨單簽名 | `load_classifier(model_dir, *, threads)`、`top_class(scores)`、`measure_runtime(classifier, texts, *, batch_size, threads)` 都符合 `test_stage8_interfaces.py`。`evaluate_model`、`evaluate_by_board` 新加的 keyword-only `batch_size` 有預設值 100，`bert-integration` 照舊的寫法呼叫也能用 |
| 第一輪問題 1（分批推論） | 已修。`_predict_in_batches` 依 `batch_size` 切批推論，`batch_size` < 1 會拒絕；`main()` 從 `InferenceSettings` 讀 batch_size 傳給 `evaluate_model`、`evaluate_by_board`、`measure_runtime`。因此記憶體峰值 `ru_maxrss` 不會再被整批推論撐大，可以對應 shadow 的 `INFERENCE_BATCH_SIZE`（D-023）。單元測試確認分批為 [10,10,10,6]、`evaluate_by_board` 有把 batch_size 傳下去、`batch_size=0` 會被拒絕。7.27 已補上對應的句子 |
| 模型包格式與 ONNX | `input_ids`、`attention_mask` 為 int64，有 `token_type_ids` 輸入時餵全 0；輸出取 `logits`，依 `card.labels` 做 softmax；truncation 長度用 `card.max_len`，`max_len` 為 None 時拒絕載入；padding 用 `[PAD]` id；`intra_op_num_threads = threads`，只用 CPUExecutionProvider。以上都符合 7.27 |
| sklearn 與舊卡片 | 「缺類補 0」已搬進 `SklearnClassifier`；sklearn 走 `train.load_model`，舊 baseline 卡片照常載入 |
| 7.27 回寫 | 新增的 5 行都和程式一致；只動 7.27 |
| 寫死設定、安全 | 沒有寫死的設定：`DEFAULT_BATCH_SIZE` 與 `InferenceSettings.batch_size` 的預設相同，只當函式參數的預設值。ONNX 與 JSON 載入時不執行程式；joblib 只用在本機訓練的 sklearn baseline（現狀） |
| 規範 | 有 type hints；註解、docstring 都不超過 3 行；log 沿用 `radar.common.log` |
| 測試是否涵蓋驗收條件 | 三類齊全、總和為 1、缺類補 0、空輸入、同分、fp32／int8、舊卡片、threads、runtime 欄位、暖機、nearest-rank、參數錯誤，都有驗收測試或單元測試 |
| 實際驗證 | `uv run pytest tests/unit/acceptance/bert-classifier tests/unit/ml -q` 的結果是 302 passed。`uv run ruff check src tests` 結果是 All checks passed。`grep -rn "TODO(bert-classifier)" src tests` 只命中驗收測試自己的檢查字串（第 289 行）。PR 的 CI：Check、Integration Test、Security 都是 pass |

## 不擋合併（建議，沿用第一輪）

- `evaluate.py` 的 `main()` 先跑 `evaluate_model`，又跑 `evaluate_by_board`，每篇等於推論兩次；`measure_runtime` 再推論第三次（這次是量耗時，本來就要跑）。BERT 的評估時間因此約多出一倍，結果不受影響。之後可以先預測一次，再依看板分組計算。
- `measure_runtime` 對 sklearn baseline 也會寫「INFERENCE_THREADS = N」，但 sklearn 不使用這個設定。只影響報告的解讀。
