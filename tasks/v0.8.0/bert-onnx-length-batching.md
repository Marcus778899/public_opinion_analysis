# 派工單 bert-onnx-length-batching

- **類型**：feat
- **負責**：backend
- **目標**：ONNX 推論依 token 長度排序後切小批，每次 `session.run` 的篇數 × 序列長度不超過 `INFERENCE_MAX_BATCH_TOKENS`，預測不變、耗時與記憶體下降，讓 ckip fp32 有機會過進 shadow 門檻
- **背景**：ckip fp32 evaluate 每批 100 篇約 70 秒、RSS 約 5 GB（門檻 30 秒、1.2 GB）；主因是每批補到 512 token 的中間張量（#193 分析）。這是 7.27 進 shadow 順序 2；完成後甲方重跑 evaluate（順序 3）
- **設計依據**：`docs/development-spec.md` 7.27「評估結果與進 shadow 的調整」的「修正單」表 `bert-onnx-length-batching` 列與「本節自行決定」表（負責檔案、驗收條件、預設 4096 以該節為準）
- **相依**：bert-evaluate-report-fix（已合併）
- **負責檔案**：
  - `src/radar/ml/training/classifier.py`
  - `src/radar/common/settings.py`
  - `.env.example`
  - `src/radar/ml/inference/main.py`
  - `src/radar/ml/training/evaluate.py`
  - `tests/unit/ml/test_stage8_interfaces.py`
  - `tests/unit/ml/training/test_classifier.py`
- **禁區**：不改模型包格式、`max_len`、預測與機率的計算方式；不改驗收測試（含 `tests/unit/acceptance/bert-classifier/`）；`INFERENCE_MAX_BATCH_TOKENS` 為選填（`.env.example` 寫成註解，D-009）
- **驗收測試**：
  - `tests/unit/acceptance/bert-onnx-length-batching/`
- **驗收條件**：
  - [ ] 打亂長短的輸入，分小批結果與整批一次推論的機率差 < 1e-5，輸出順序與輸入一致
  - [ ] 每次 `session.run` 的篇數 × 序列長度 ≤ 上限；單篇超過上限時單獨一批
  - [ ] `InferenceSettings.max_batch_tokens` 預設 4096、須 ≥ `card.max_len`；`load_classifier` 加 keyword-only `max_batch_tokens`，inference 與 evaluate 的 `main()` 都傳入設定值
  - [ ] `tests/unit/acceptance/bert-classifier/`、本單驗收測試、`make check` 通過；`grep -rn "TODO(bert-onnx-length-batching)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/bert-onnx-length-batching tests/unit/acceptance/bert-classifier tests/unit/ml`；`make check`
- **回報檔**：`reports/bert-onnx-length-batching.json`

## 執行資訊（task.py 產生）

- Issue：#196
- 分支：`feat/bert-onnx-length-batching`（從 develop 開出）
- 工作目錄：`.worktrees/bert-onnx-length-batching`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-28

### CI Integration Test 失敗（manager，PR #197 @ 7004c5a）

- 失敗：`tests/integration/acceptance/bert-shadow-inference/test_shadow_service.py` 10 個測試全部「服務沒有處理到結尾事件就結束了」；log：`TypeError in radar.ml.inference.main.main (main.py:183): env.<locals>.<lambda>() got an unexpected keyword argument 'max_batch_tokens'`
- 原因：該檔的 fake 以 lambda 替換 `load_classifier`，不接受本單依 7.27 新增的 keyword `max_batch_tokens`；7.27「修正單」表沒列到這個檔
- qa、worker 都只跑了 `tests/unit`；這輪必須跑整合測試（`docker compose --env-file .env -f .worktrees/bert-onnx-length-batching/compose.yaml run --rm test`，做完 `down -v`）

### 範圍更新（manager，取代原欄位）

- **驗收測試**：
  - `tests/unit/acceptance/bert-onnx-length-batching/`
  - `tests/integration/acceptance/bert-shadow-inference/test_shadow_service.py`（只由 qa 修改：讓 fake 接受 `max_batch_tokens`，並驗證 inference `main()` 有傳入設定值；其他斷言不動）

### 處理順序

1. qa「A」依上面修改該整合驗收測試並 commit，manager 重新 lock
2. 原 worker：不改測試；跑整合測試（指令見上）確認全過，更新回報後交回
