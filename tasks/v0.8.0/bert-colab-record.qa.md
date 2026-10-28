PASS 8e6de08

# bert-colab-record 驗證

## 逐項比對（新節 vs 派工單背景）
- epoch 表 1/2/3：0.986442/0.500538、0.875128/0.576880、0.937084/0.600676，一致；training loss 0.7747、552 步 5 分 01 秒（前 50 步 19 秒）、最佳 epoch 3、F1 0.6007，一致
- 資料名稱、3,268 筆、驗證集 10%、T4／Python 3.13，一致
- 匯出：tokenizer 一致、GPU 對 CPU 1.80e-03、CPU 對 ONNX 1.55e-06（門檻 1e-3）、不一致 0 篇、fp32 ONNX 0.6007，一致
- int8：0.5251、差 0.0755、警告線 0.03，一致；7.27 的 0.02＋耗時規則與 development-spec.md 1375 行一致
- 兩個模型包檔名、大小（379935103、59999755）、SHA-256 逐字相同
- ckip 0.6806（epoch 2）、舊 notebook 沒打包，一致
- 節內多出的 2.17e-3 非背景數字，但出自 development-spec.md 1264 行與 tasks/notebook-logits-check-fix.md，有來源

## 禁區
- `git diff develop --stat`：僅 docs/reports/model-evaluation.md、60 行新增、0 行刪除，既有內容未改
- 沒有人工測試集分數，標「待 evaluate」；沒有下切換模型的結論（待辦 4 寫「依 7.27 自行決定」）
- 註明驗證集 F1 是切出的 10%，選模型以人工測試集為準
- 備註（不構成 FAIL）：int8 段「採用的機會不大」是依驗證集的推測，且明說仍待 evaluate；不是切換模型結論

## 驗證指令
`pre-commit run --files docs/reports/model-evaluation.md`：trailing whitespace、end of files、ruff format 皆 Passed，其餘 Skipped；工作目錄無未提交變更。

## 驗收條件
- 新節含環境、資料、訓練設定引用 7.27、epoch 表、匯出驗證（含 GPU/CPU 診斷證實 #187 推測）、int8 意涵、模型包、待辦：通過
- 註明驗證集 F1 非人工測試集：通過
- 數字與背景一致、繁中精簡：通過
