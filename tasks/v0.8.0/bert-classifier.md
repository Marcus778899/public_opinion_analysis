# 派工單 bert-classifier

- **類型**：feat
- **負責**：backend
- **目標**：`Classifier` 介面的 sklearn 與 ONNX 實作、`load_classifier` 依 `model_card.kind` 載入；`evaluate` 改用它，並輸出 CPU 推論耗時（每篇 p50／p95、每批耗時、`INFERENCE_THREADS`）與程序記憶體峰值
- **背景**：階段 8（D-019～D-021、D-023）。骨架已由 `bert-skeleton`（PR #156）建好，介面簽名在 `tests/unit/ml/test_stage8_interfaces.py`；測試用小模型用 `tests/helpers/onnx_model.py`（只呼叫、不修改）
- **設計依據**：`docs/development-spec.md` 7.27「載入」「模型包格式」「測試」「檔案分工」
- **相依**：bert-skeleton（已合併）
- **負責檔案**：
  - `src/radar/ml/training/classifier.py`
  - `src/radar/ml/training/evaluate.py`
  - `tests/unit/ml/training/test_classifier.py`
  - `tests/unit/ml/training/test_evaluate.py`
- **禁區**：`ml/inference/main.py` 改用 `load_classifier` 屬於 `bert-shadow-inference`；不改骨架的簽名（要改先回報 manager）；不改 helper 與驗收測試
- **驗收測試**：`tests/unit/acceptance/bert-classifier/`
- **驗收條件**：
  - [ ] `predict_proba` 三類齊全、總和為 1；sklearn 實作吸收原「缺類補 0」邏輯；ONNX 實作以 `threads` 限制 intra-op thread
  - [ ] fp32 與 int8 小模型都能載入與推論；舊 baseline 卡片（無新欄位）照常載入
  - [ ] `evaluate` 的輸出含耗時與記憶體峰值欄位
  - [ ] `grep -rn "TODO(bert-classifier)" src tests` 沒有結果
  - [ ] 驗收測試與 `make check` 通過；PR 的 CI 全綠
- **驗證指令**：`uv run pytest tests/unit/acceptance/bert-classifier tests/unit/ml`；`make check`
- **回報檔**：`reports/bert-classifier.json`

## 執行資訊（task.py 產生）

- Issue：#157
- 分支：`feat/bert-classifier`（從 develop 開出）
- 工作目錄：`.worktrees/bert-classifier`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-22

### 負責檔案更新（manager，取代原欄位：同一個 PR 內回寫 7.27）

- **負責檔案**：
  - `src/radar/ml/training/classifier.py`
  - `src/radar/ml/training/evaluate.py`
  - `tests/unit/ml/training/test_classifier.py`
  - `tests/unit/ml/training/test_evaluate.py`
  - `docs/development-spec.md`

### 要做的事

- 把回報裡列的實作決定（evaluate 簽名改吃 `Classifier`、`measure_runtime` 暖機與 nearest-rank、`render_markdown` 的 runtime 節格式、`main()` 讀 `INFERENCE_THREADS`／`INFERENCE_BATCH_SIZE`、ONNX padding 與 `max_len` 為 None 拒絕載入）精簡回寫到 `docs/development-spec.md` 7.27（「載入」或「測試」附近，或「自行決定」表），只改 7.27，不動其他節
- 重跑 `make check`，更新 `reports/bert-classifier.json`

## 追加 2026-10-22

### reports/bert-classifier.review.md

REQUEST_CHANGES 69b92ae

## 檢查範圍

PR #161（`gh pr diff 161`），對照派工單 `tasks/bert-classifier.md`（含 2026-10-22 追加）與開發規格 7.27「載入」「模型包格式」「測試」「檔案分工」。

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改了 classifier.py、evaluate.py、兩個單元測試、`docs/development-spec.md`（只動 7.27「載入」）；驗收測試目錄只有 qa 的 `755e0f0 test(bert-classifier)` commit 改過；helper、`inference/main.py` 沒改 |
| 跨單簽名 | `load_classifier(model_dir, *, threads)`、`top_class(scores)`、`measure_runtime(classifier, texts, *, batch_size, threads)` 符合 `tests/unit/ml/test_stage8_interfaces.py` |
| bert-shadow-inference 能不能直接接上 | 可以：`load_classifier` 回傳 `(Classifier, ModelCard)`，兩種實作空輸入都回 `[]`、三類齊全；`top_class` 的同分規則（Polarity 宣告順序）與現行 `inference/main.py` 的 `predict()` 一致，`Predictor` 把 `pipeline` 換成 `Classifier` 後，用 `top_class(scores)` 就能取代 `predict()` |
| 模型包格式 | 輸入 `input_ids`、`attention_mask` int64，有 `token_type_ids` 時餵全 0；輸出取 `logits`，依 `card.labels` 做 softmax；tokenizer 用 `Tokenizer.from_file`，truncation 到 `max_len`、batch 內 padding：都符合 |
| threads | `intra_op_num_threads = threads`，只用 CPUExecutionProvider |
| 舊 baseline 卡片 | sklearn 走 `train.load_model`；新欄位都有預設值，可以照常載入（單元測試與驗收測試都有測） |
| 7.27 回寫與實作 | 5 行都和程式一致（PAD id、`max_len` 為 None 時拒絕、`top_class`、暖機＋nearest-rank、`_clock`／`_peak_rss_mb`、runtime 節格式、`InferenceSettings`） |
| 寫死設定、安全 | 沒有寫死設定（threads、batch_size 從 `InferenceSettings` 讀）；ONNX 與 JSON 載入時不執行程式；joblib 只用在 sklearn baseline（現狀） |
| 測試 | 單元測試涵蓋正常、缺類補 0、空輸入、同分、max_len 為 None、缺卡片、暖機、百分位、參數錯誤、runtime 節有和沒有兩種情況；本機 `uv run pytest tests/unit/acceptance/bert-classifier tests/unit/ml` 結果 299 passed；`grep TODO(bert-classifier)` 只命中驗收測試自己的檢查字串；PR 的 CI（Check、Integration Test、Security）都綠 |

## 要修的問題

1. `src/radar/ml/training/evaluate.py:117`：`evaluate_model` 把整個測試集一次丟進 `classifier.predict_proba`，沒有分批。
   - 對 sklearn 沒有影響，但 ONNX BERT 會出問題。人工測試集有 300 篇（開發規格 S3-04），`max_len` 預設 512，一次推論 300 篇時，光是一層的 attention 機率就約 300×12×512×512×4 B ≈ 3.8 GB。
   - `measure_runtime` 量到的是 `ru_maxrss`，也就是整個程序的歷史峰值。這次峰值發生在 `main()` 第 281～282 行的整批推論，不是在 `INFERENCE_BATCH_SIZE` 的分批推論裡。所以 `evaluation.md` 的「記憶體峰值」不能拿來判斷 shadow 的 1.5g 上限（D-023），反而會誤導甲方在步驟 9 的選擇；在甲方的機器上也可能直接 OOM。
   - 改法：`evaluate_model`（以及經由它的 `evaluate_by_board`）改成每次推論 `batch_size` 篇。例如在 evaluate.py 加一個分批預測的小函式，再給 `evaluate_model`／`evaluate_by_board` 加一個 keyword-only 的 `batch_size`，`main()` 傳 `settings.batch_size` 進去。這兩個函式不在跨單簽名表裡，可以改，但要給預設值，`bert-integration` 才不受影響。
   - 補單元測試：用 `FakeClassifier.calls` 確認每次呼叫都不超過 `batch_size` 篇。
   - 7.27「載入」補一句「評估也依 `INFERENCE_BATCH_SIZE` 分批推論，記憶體峰值才對應 shadow 的設定」。

## 不擋合併（建議）

- `evaluate.py:151`、`:282`：`evaluate_by_board` 會把每篇再推論一次，BERT 的評估時間因此變成兩倍。可以先預測一次，再分組計算；這次順手改或之後再改都可以。
- `measure_runtime` 對 sklearn baseline 也會寫「INFERENCE_THREADS = N」，但 sklearn 其實不使用這個設定。只影響報告的解讀，不用改。
