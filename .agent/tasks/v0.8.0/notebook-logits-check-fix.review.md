APPROVE 6773e11

# Review PR #187 notebook-logits-check-fix 第 2 輪（commit 6773e11）

## 檢查範圍

| 項目 | 結果 |
|---|---|
| 改動檔案 ⊂ 負責檔案 | OK：第 2 輪（138e75a..6773e11）只改 notebook、`tests/unit/ml/notebook/test_notebook_cells.py`、spec 7.27 兩列；驗收測試目錄只有 qa 的 `test(...)` commit 9095224 |
| 禁區（訓練參數、revision、模型包格式、套件） | 沒動 |
| 打包前比對、超標不打包、ids 檢查保留 | OK：cell 7 `if max_diff >= LOGITS_TOLERANCE: raise` 仍在 `build_package` 之前；`hf_ids != tk_ids` 沒動 |
| notebook 無輸出、寫死設定值 | OK：outputs 0、execution_count 全為 None；沒有新的寫死值 |
| 實際執行 | `uv run pytest -q tests/unit/acceptance/notebook-logits-check-fix tests/unit/ml/notebook` → 27 passed |

## 前一輪問題

| # | 結果 |
|---|---|
| 1 推論寫成實測 | 已改：7.27 改成「GPU PyTorch 對 CPU ONNX 曾差 2.17e-3，推測來自裝置間 fp32 運算差異（未實測，見 #178）」；cell 7 NOTE 也改成推測語氣 |
| 2 沒留診斷資訊 | 已改：門檻判斷前用訓練後留在 GPU 的 `model` 跑同一組 `tk_ids`，印出「GPU PyTorch 對 CPU PyTorch」最大差，不擋；7.27 已註明；單元測試 `test_logits_check_prints_gpu_vs_cpu_diff_without_raising` 確認有印出、位置在門檻判斷前、沒有 raise。AMP 的主權重是 fp32，`run_torch` 在 `no_grad` 下沒有 autocast，所以診斷值確實是 GPU fp32 對 CPU fp32；沒有 GPU 時 `model` 在 CPU，診斷值是 0，不影響門檻判斷 |
| 建議 A | 已採用：預測類別不一致只印篇數，7.27 同步說明 |
| 建議 B | 已採用：`run_torch` 跟 `run_onnx` 一樣依長度排序分批，兩邊的 padding 寬度一致 |
| 建議 C | 已採用：措辭改成「釘版套件帶進來的 `huggingface_hub`」 |

## 做法判斷

CPU fp32 重新載入比對、門檻維持 1e-3、診斷值只印不擋，這套做法兩個 BASE 都適用（都用 `save_model` 存 safetensors 再重新載入）。差異來源要等甲方在 Colab 重跑，看印出的診斷值才能確認（#178）。這屬於環境限制，不擋合併。

## 備註（不擋合併）

- README 第 70 行要不要同步 diffusers 的說明，依 worker 回報交給 manager 決定。

問題數量：0
