PASS c952ec0

# 驗證 bert-colab-record-ckip（docs、fast）

## 驗收條件

1. ckip 數字逐項比對派工單背景，全部一致：
   - 訓練 552 步 4 分 27 秒（前 50 步 20 秒）；epoch 表 0.973544/0.553683、0.771341/0.680656、0.829063/0.649934；epoch 3 training loss 0.7811；選 epoch 2、0.6807
   - tokenizer 一致；GPU 對 CPU 1.21e-03；CPU 對 ONNX 2.65e-06（門檻 1e-3）；不一致 0 篇；fp32 ONNX 0.6807
   - int8 0.6377、差 0.0430、超過 0.03 警告
   - `bert-ckip-202610280849.zip` 379880582 / 0601f989...1038；`bert-ckip-202610280849-int8.zip` 62503412 / f18ba402...e64de19e（完整 64 字元逐字相符）
2. 並列表存在，欄位齊全（fp32／int8、int8 掉分、ONNX 差、GPU／CPU 差、訓練時間、包大小），並註明「驗證集分數，不是人工測試集；選模型以人工測試集為準（7.27）」。macbert 欄位（0.6007、0.5251、0.0755、1.55e-06、1.80e-03、5 分 01 秒、379935103／59999755）與同節既有 macbert 紀錄逐項一致。
3. 待辦為：1. 四個包 import_model（ckip 重跑已完成）；2. evaluate；3. 依 7.27 選模型。符合。舊的「ckip 重跑」待辦已移除，舊 0.6806 已改為「不再採用」。

## 禁區

- `git diff develop` 只動 `docs/reports/model-evaluation.md`，且只在「階段 8 BERT」一節（@@ -236 起）；macbert 段落沒有任何被刪或改的行（被刪的 6 行只有 ckip 佔位與舊待辦）。
- 沒有人工測試集分數；沒有選模型或切換結論（待辦第 3 項仍是待決）。

## 指令

`pre-commit run --files docs/reports/model-evaluation.md`：trailing whitespace、end of files、ruff format 皆 Passed，其餘 Skipped（無對應檔案）。

## 備註（不構成 FAIL）

- 回報提到 docs/reports 在 .gitignore，commit 需 `git add -f`；檔案已被追蹤，diff 正常顯示。
- 無寫死設定值、無測試需要（docs 單，驗收測試：無）。
