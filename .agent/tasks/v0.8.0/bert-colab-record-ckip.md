# 派工單 bert-colab-record-ckip

- **類型**：docs
- **負責**：backend
- **通道**：fast
- **目標**：在 `docs/reports/model-evaluation.md` 的「階段 8 BERT：Colab fine-tune 紀錄」一節補上 ckip 這次執行的結果，並把兩個模型並列比較
- **背景**：甲方 2026-10-28 用新版 notebook（同 macbert 那次、同資料）在 Colab 跑 `BASE = "ckip"`，輸出原樣照錄：訓練 552 步 4 分 27 秒（前 50 步 20 秒）；各 epoch 驗證 loss／macro-F1：1：0.973544／0.553683、2：0.771341／0.680656、3：0.829063／0.649934（epoch 3 training loss 0.7811），選最佳 epoch 2，PyTorch 驗證集 macro-F1 0.6807。匯出：tokenizer ids 一致；診斷 GPU 對 CPU 最大差 1.21e-03；PyTorch（CPU）對 ONNX 最大差 2.65e-06（門檻 1e-3）；預測類別不一致 0 篇；fp32 ONNX macro-F1 0.6807。int8：macro-F1 0.6377（差 0.0430，超過 0.03 警告）。模型包：`bert-ckip-202610280849.zip` size 379880582 sha256 0601f989e0007addab32abd29c7081cfa5a69a5776ba53672c028027332c1038；`bert-ckip-202610280849-int8.zip` size 62503412 sha256 f18ba402f987389a9883cc537f9083bbb94cefbea77966060982a340b64de19e。上一節原本記的「先前 ckip（舊 notebook）0.6806」改為以這次為準
- **設計依據**：`docs/development-spec.md` 7.11、7.27；#178
- **相依**：無
- **負責檔案**：
  - `docs/reports/model-evaluation.md`
- **禁區**：只改「階段 8 BERT：Colab fine-tune 紀錄」一節；不改 macbert 的數字；不寫人工測試集分數（待 evaluate）；不下選模型或切換的結論
- **驗收測試**：無
- **驗收條件**：
  - [ ] ckip 的 epoch 表、匯出驗證、int8、兩個模型包檔名／大小／SHA-256 與本單背景一致
  - [ ] 有一張 macbert 與 ckip 並列的摘要表（驗證集 fp32／int8 macro-F1、int8 掉分、ONNX 差、GPU／CPU 差、訓練時間、包大小），並註明選模型以人工測試集為準
  - [ ] 待辦更新為：4 個包 import_model、evaluate（ckip 重跑已完成）
- **驗證指令**：`pre-commit run --files docs/reports/model-evaluation.md`
- **回報檔**：`reports/bert-colab-record-ckip.json`

## 執行資訊（task.py 產生）

- Issue：#190
- 分支：`docs/bert-colab-record-ckip`（從 develop 開出）
- 工作目錄：`.worktrees/bert-colab-record-ckip`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
