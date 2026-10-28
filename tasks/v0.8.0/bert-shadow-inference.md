# 派工單 bert-shadow-inference

- **類型**：feat
- **負責**：backend
- **目標**：推論服務支援 `INFERENCE_ROLE=shadow`：改用 `load_classifier`，shadow 寫 `predictions.shadow`、從 `predictions_shadow` 載入快取，移除骨架的 `require_primary`
- **背景**：階段 8（D-020、D-023）。骨架已由 `bert-skeleton`（PR #156）建好：`InferenceRole`、`ml/inference/roles.py` 對照表、topic、migration `0006`、compose 的 `inference-shadow`。`Classifier` 實作由平行的 `bert-classifier` 做，這張單的測試用 `tests/unit/ml/fakes.py` 的 `FakeClassifier`
- **設計依據**：`docs/development-spec.md` 7.27「shadow 並行」「載入」「測試」「威脅與對策」；設計文件 8.4
- **相依**：bert-skeleton（已合併）
- **負責檔案**：
  - `src/radar/ml/inference/main.py`
  - `tests/unit/ml/inference/`
  - `tests/integration/ml/test_inference_cache.py`
  - `tests/integration/ml/test_inference_consumer.py`
  - `tests/integration/ml/test_inference_shadow.py`
  - `tests/integration/conftest.py`
- **禁區**：`tests/unit/ml/inference/test_roles.py`、`roles.py`、`settings.py`、`classifier.py` 不改；group、topic、表名只能從 `roles.py` 取；primary 的行為與 `predictions` 的寫入不變
- **驗收測試**：`tests/integration/acceptance/bert-shadow-inference/`
- **驗收條件**：
  - [ ] shadow 只寫 `predictions.shadow`，`predictions_shadow` 有資料、`predictions` 沒有 shadow 版本
  - [ ] consumer group 為 `inference-shadow-<model_version>`；重啟從 `predictions_shadow` 載入快取
  - [ ] `tests/integration/conftest.py` 的 `CLICKHOUSE_TOPICS` 加入 `names.PREDICTIONS_SHADOW`
  - [ ] 現行 primary 推論的單元與整合測試不受影響；consumer 的冪等與 DLQ 有測試
  - [ ] `grep -rn "TODO(bert-shadow-inference)" src tests` 沒有結果
  - [ ] 整合測試前 `docker compose ls` 確認沒有其他測試堆疊，做完 `down -v`；PR 的 CI 全綠
- **驗證指令**：`make check`；`docker compose --env-file .env -f .worktrees/bert-shadow-inference/compose.yaml run --rm test`
- **回報檔**：`reports/bert-shadow-inference.json`

## 執行資訊（task.py 產生）

- Issue：#159
- 分支：`feat/bert-shadow-inference`（從 develop 開出）
- 工作目錄：`.worktrees/bert-shadow-inference`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-22

### 負責檔案更新（manager，取代原欄位：同一個 PR 內同步 7.27）

- **負責檔案**：
  - `src/radar/ml/inference/main.py`
  - `tests/unit/ml/inference/`
  - `tests/integration/ml/test_inference_cache.py`
  - `tests/integration/ml/test_inference_consumer.py`
  - `tests/integration/ml/test_inference_shadow.py`
  - `tests/integration/conftest.py`
  - `docs/development-spec.md`

### 要做的事（bert-classifier 已合併 PR #161，分支已 sync 到 develop）

- `main.py` 改用 `radar.ml.training.classifier` 的正式 `top_class`（與 `load_classifier`），刪掉本地暫時版
- 開發規格 7.27「shadow 並行」中「骨架期間 `main()` 遇到 `shadow` 拒絕啟動（`require_primary`），由 `bert-shadow-inference` 移除」改成現況；回報 open_questions 3、4（`predict()` 移除、`load_cache` 的 `table` 參數）有影響文件描述的一併同步；只改 7.27 這幾處（同節 D-025 相關句子由 bert-notebook 改，不要動）
- 重跑 `make check` 與整合測試（跑前 `docker compose ls` 確認沒有其他測試堆疊，做完 `down -v`），更新 `reports/bert-shadow-inference.json`
