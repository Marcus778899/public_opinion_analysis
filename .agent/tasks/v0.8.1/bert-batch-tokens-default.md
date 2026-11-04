# 派工單 bert-batch-tokens-default

- **類型**：fix
- **負責**：backend
- **目標**：`INFERENCE_MAX_BATCH_TOKENS` 預設由 4096 改為 2048（程式、`.env.example`、開發規格 7.27 一起改）
- **背景**：shadow 容器（D-023：2 CPU、1.5g）實測 ckip fp32 512 版：4096 時 RSS 1268 MB 超過 7.27 門檻 1.2 GB；2048 時 RSS 997 MB、每批 p50 23.8 s／最大 30.5 s、macro-F1 0.612 不變，全過門檻。證據：`reports/shadow-memory-measure.json`。預設值應改成在容器內能過門檻的值
- **設計依據**：`docs/development-spec.md` 7.27「評估結果與進 shadow 的調整」（順序表第 2 列、順序 3 判定、修正單表 `bert-onnx-length-batching` 列、「本節自行決定」的 `INFERENCE_MAX_BATCH_TOKENS` 預設列）
- **相依**：無
- **負責檔案**：
  - `src/radar/common/settings.py`
  - `src/radar/ml/training/classifier.py`
  - `.env.example`
  - `docs/development-spec.md`（只改 7.27 裡預設值相關文字，並在順序 3 判定附近補一行容器內實測結果：4096／2048／1024 三列，數字取自上面證據檔）
  - `tests/unit/ml/training/test_classifier.py`（若有依賴預設值的測試）
  - `tests/unit/acceptance/bert-onnx-length-batching/test_length_batching_acceptance.py`（只限 qa 改 `test_settings_default_max_batch_tokens_is_4096` 一個測試）
  - `tests/unit/acceptance/bert-batch-tokens-default/`
- **禁區**：不改分批演算法、`load_classifier` 簽名以外的行為；不碰 `models/`、compose 檔
- **驗收測試**：
  - `tests/unit/acceptance/bert-batch-tokens-default/`
- **驗收條件**：
  - [ ] 未設環境變數時 `InferenceSettings().max_batch_tokens == 2048`；`load_classifier` 的 `max_batch_tokens` 預設與 `DEFAULT_MAX_BATCH_TOKENS` 皆為 2048
  - [ ] `.env.example` 註解與範例值為 2048
  - [ ] 開發規格 7.27 不再把 4096 寫成預設；容器內實測結果已記錄
  - [ ] 驗收測試、`make check` 通過；`grep -rn "TODO(bert-batch-tokens-default)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/bert-batch-tokens-default tests/unit/acceptance/bert-onnx-length-batching tests/unit/ml`；`make check`
- **回報檔**：`reports/bert-batch-tokens-default.json`

## 執行資訊（task.py 產生）

- Issue：#205
- 分支：`fix/bert-batch-tokens-default`（從 develop 開出）
- 工作目錄：`.worktrees/bert-batch-tokens-default`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
