PASS 6773e11

# QA notebook-logits-check-fix（第 2 輪，commit 6773e11）

## 實際執行
- `uv run pytest tests/unit/acceptance/notebook-logits-check-fix tests/unit/ml/notebook` → `27 passed in 0.07s`
- `uv run pytest tests/unit -q -n 4` → `1360 passed in 4.31s`
- `uv run ruff check .` → All checks passed；`ruff format --check .` → 288 files already formatted
- `pre-commit run --all-files` → 全部 Passed（含 ruff、bandit、end of files）
- `grep -rn "TODO(notebook-logits-check-fix)" src tests` → 無結果
- 驗收測試檔相對 develop 只由 test commit 9095224 新增，worker commit 未改

## 驗收條件
1. 回報寫明差異來源與做法：OK。回報 open_questions 說明為推測（#178 追蹤）、改 CPU fp32 重新載入比對、門檻維持 1e-3；7.27 說明 O(0.1～1) 的匯出錯誤仍擋得住。
2. 打包前仍比對、超標仍 raise、ids 檢查保留：OK。`if max_diff >= LOGITS_TOLERANCE: raise` 在 `build_package` 之前；`hf_ids != tk_ids` 檢查未動（驗收測試覆蓋）。
3. 7.27 補 diffusers：OK（Colab 套件版本列，措辭已依建議 C 改為「釘版套件帶進來的 huggingface_hub」）。
4. 測試、check、notebook 無輸出：OK（`test_notebook_has_no_outputs` 通過）。

## review 必改項確認
- 問題 1（推論寫成實測）：已改。7.27 為「推測來自裝置間 fp32 運算差異（未實測，見 #178）」；notebook NOTE 也是推測語氣。
- 問題 2（留診斷資訊）：已做。門檻判斷前以留在 GPU 的 `model` 跑同一組 `tk_ids`，印出「GPU PyTorch 對 CPU PyTorch」最大差，不擋；7.27 註明會印；單元測試 `test_logits_check_prints_gpu_vs_cpu_diff_without_raising` 確認印出、位置在門檻判斷前、無 raise。
- 建議 A（argmax 只印出）、B（run_torch 同樣依長度排序）、C 皆已落實，各有單元測試。

## 靜態檢查
- `FINAL_DIR`、`AutoModelForSequenceClassification`、`torch`、`model` 在 cell 7 之前已定義，無 `del model`；`trust_remote_code=False` 保留。
- 無新增寫死設定值或套件。

## 未驗證項目（無真實 Colab）
- notebook 實際在 Colab 執行：CPU 重新載入後與 ONNX 的差是否 < 1e-3、GPU 對 CPU 診斷值實際為何（甲方重跑確認，#178）。
- `torch_dtype` 參數在 transformers 4.53.3 的實際行為（review 已確認可用，未在此環境執行）。
- 這些屬環境限制，且 notebook 已加診斷輸出；不列為 FAIL。

## 提醒（非問題）
- README 第 70 行是否同步 diffusers 說明，回報交由 manager 決定。
