# 派工單 notebook-logits-check-fix

- **類型**：fix
- **負責**：backend
- **目標**：`notebooks/bert_finetune.ipynb` 的 PyTorch／ONNX logits 比對在真實 Colab 不再誤擋正常匯出的模型，同時仍能擋住真的匯出錯誤
- **背景**：甲方 2026-10-28 在 Colab（T4 GPU、Python 3.13）以 `BASE = "ckip"` 跑（#183 修正後）：tokenizer ids 一致，但「PyTorch 與 ONNX logits 最大絕對差: 2.17e-03（門檻 0.001）」→ AssertionError 不打包。目前 `run_torch` 用訓練後留在 GPU 上的模型，ONNX 在 CPU 執行；訓練用 fp16（混合精度）。門檻 1e-3 來自開發規格 7.27「匯出」段。先查清差異來源，再決定做法（例：比對的裝置與精度、門檻的定義），不要只把數字調大了事；macbert 尚未跑，做法要兩個 BASE 都適用。另：#183 review 指出 7.27 沒寫第一格會移除 Colab 預裝的 diffusers，同一個 PR 補上
- **設計依據**：`docs/development-spec.md` 7.27「匯出」、「測試」、「自行決定」表；`reports/notebook-onnx-export-fix.review.md`
- **相依**：notebook-onnx-export-fix（已合併）
- **負責檔案**：
  - `notebooks/bert_finetune.ipynb`
  - `tests/unit/ml/notebook/`
  - `docs/development-spec.md`（只改 7.27 與本單有關的句子）
- **禁區**：不改訓練參數、revision、模型包格式；不新增套件；notebook 不帶輸出；不改驗收測試
- **驗收測試**：
  - `tests/unit/acceptance/notebook-logits-check-fix/`
- **驗收條件**：
  - [ ] 回報寫明差異來源的判斷依據與選擇的做法；若改門檻或比對方式，7.27 同步更新並說明為何仍能擋住匯出錯誤
  - [ ] notebook 仍在打包前比對 PyTorch 與 ONNX logits，超過門檻仍不打包；ids 一致性檢查保留
  - [ ] 7.27 補上第一格移除 diffusers 的說明
  - [ ] 驗收測試、`uv run pytest tests/unit/ml/notebook`、`make check` 通過；notebook 無輸出
- **驗證指令**：`uv run pytest tests/unit/acceptance/notebook-logits-check-fix tests/unit/ml/notebook`；`make check`
- **回報檔**：`reports/notebook-logits-check-fix.json`

## 執行資訊（task.py 產生）

- Issue：#186
- 分支：`fix/notebook-logits-check-fix`（從 develop 開出）
- 工作目錄：`.worktrees/notebook-logits-check-fix`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-28

### reports/notebook-logits-check-fix.review.md

REQUEST_CHANGES 138e75a

# Review PR #187 notebook-logits-check-fix（commit 138e75a）

## 檢查範圍

| 項目 | 結果 |
|---|---|
| 改動檔案 ⊂ 負責檔案 | OK：notebook、`tests/unit/ml/notebook/test_notebook_cells.py`、spec 7.27 兩列；驗收測試只有 qa 的 `test(...)` commit 9095224 新增，worker commit 沒碰 |
| 禁區（訓練參數、revision、模型包格式、套件） | 沒動 |
| 打包前仍比對、超標仍不打包、ids 檢查保留 | OK（cell 7：`max_diff >= LOGITS_TOLERANCE` raise 在 `build_package` 前；`hf_ids != tk_ids` 檢查沒動） |
| 重新載入的權重與 ONNX 同源 | OK：`trainer.save_model(FINAL_DIR)` 在 `load_best_model_at_end` 之後，`optimum-cli --model FINAL_DIR` 與 `cpu_model` 讀同一份；AMP（`fp16=True`）的主權重是 fp32，存檔也是 fp32；`torch_dtype` 在釘版的 transformers 4.53.3 可用；兩個 BASE 存檔都走 `save_model`（safetensors），重新載入路徑相同 |
| notebook 無輸出、寫死設定值 | OK |
| 測試 | 驗收測試鎖住不變條件；單元測試用子字串確認 CPU 重新載入與 argmax 檢查，夠用 |

## 做法判斷

- **CPU fp32 重新載入比對：合理，建議保留。** 不管差異來源是不是裝置，這個比對都比原本好：參考端跟 ONNX 一樣在 CPU 上算、跟推論端的部署條件一致，也順便驗到存檔。
- **門檻維持 1e-3：合理。** 匯出錯誤（權重沒載入、圖接錯、輸入名對錯）造成的 logits 差異是 O(0.1～1)，1e-3 仍擋得住。
- **差異來源：推論沒有實測佐證，文件卻寫成實測事實（見問題 1）。** 2.17e-3 量到的是「GPU PyTorch 對 CPU ONNX」，不是「GPU 對 CPU」。在 T4（Turing，沒有 TF32）上，BERT-base 的 fp32 結果在 GPU 和 CPU 之間通常只差 1e-5～1e-4。2.17e-3 偏大，也可能是 SDPA 在 GPU 和 CPU 選到不同 kernel、遮罩常數不同或其他原因。這個 PR 沒有留下能分辨原因的資訊：甲方重跑時如果仍超標，還是只能再猜一次（見問題 2）。
- **argmax 一致檢查：沒有增加偵測力（不擋合併，見建議 A）。** 只要最大差 < 1e-3，argmax 不一致就只會發生在兩類 logits 相差 < 2e-3 的近似平手樣本，那是數值平手而不是匯出錯誤。所以這個檢查只會增加誤擋，擋不到新的錯誤。抽樣 64 篇遇到的機率很低。

## 要改的問題

1. `docs/development-spec.md:1264` — 「Colab T4 實測 GPU 對 CPU 差 2.17e-3，來自 GPU 與 CPU 的 fp32 運算順序不同，不是匯出錯誤」把推論寫成實測結論。實測的是 GPU PyTorch 對 CPU ONNX，原因沒有驗證過 — 改成「Colab T4 上 GPU PyTorch 對 CPU ONNX 差 2.17e-3；推測來自裝置間 fp32 運算差異（未實測，見 #178），比對兩端統一在 CPU」。`notebooks/bert_finetune.ipynb` cell 7 的 NOTE「差異會到 1e-3 等級」也同步改成推測語氣。
2. `notebooks/bert_finetune.ipynb` cell 7（`run_torch` 之後、門檻判斷之前）— 沒有留下能驗證差異來源的資訊。下次在 Colab 仍超標時無法判斷原因 — 在門檻判斷之前，用訓練後留在 GPU 的 `model` 跑同一組 `tk_ids`，印出「GPU PyTorch 對 CPU PyTorch」的最大差（只印出、不擋），讓甲方重跑一次就能確認或推翻推論；7.27 那句也註明 notebook 會印這個值。補一個單元測試確認有印出這個值。

## 建議（不擋合併）

- A. 刪掉 argmax 一致檢查（理由見上），或改成只印出不一致的篇數。若保留，7.27「且預測類別全部一致」那句要說明它只是保險，不是靠它擋匯出錯誤。
- B. `run_torch` 依索引順序分批，`run_onnx` 依長度排序分批，兩邊同一篇文章的補齊（padding）寬度不同。有遮罩時數學上等價，但會多一個數值差的變數。可以讓 `run_torch` 也用同樣的排序，比對時只剩「實作不同」一個變數。
- C. `docs/development-spec.md:1384`「與釘版的 `huggingface_hub` 不相容」：`huggingface_hub` 沒有直接釘版本，而是釘版的 `transformers` 帶進來的。可以改成「與釘版套件帶進來的 `huggingface_hub` 不相容」，和 notebook 第一格的 NOTE 一致。其餘 diffusers 說明正確。

問題數量：2（另有 3 條不擋合併的建議）
