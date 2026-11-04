# 派工單 bert-colab-record

- **類型**：docs
- **負責**：backend
- **通道**：fast
- **目標**：在 `docs/reports/model-evaluation.md` 新增「階段 8 BERT：Colab fine-tune 紀錄」一節，記下 macbert 這次執行的結果（ckip 之後補在同一節）
- **背景**：甲方 2026-10-28 用合併 #183、#187 後的 notebook 在 Colab（T4 GPU、Python 3.13）跑 `BASE = "macbert"`，輸出如下（甲方貼的，原樣照錄數字）。資料：`groq-qwen-qwen3.8-27b-prompt-v6-202610280709`（3,268 筆，驗證集分層 10%）。訓練 552 步 5 分 01 秒（前 50 步 19 秒）；各 epoch 驗證 loss／macro-F1：1：0.986442／0.500538、2：0.875128／0.576880、3：0.937084／0.600676（epoch 3 training loss 0.7747），選最佳 epoch 3，PyTorch 驗證集 macro-F1 0.6007。匯出：tokenizer ids 一致；診斷 GPU PyTorch 對 CPU PyTorch 最大差 1.80e-03；PyTorch（CPU）對 ONNX 最大差 1.55e-06（門檻 1e-3）；預測類別不一致 0 篇；fp32 ONNX macro-F1 0.6007。int8：macro-F1 0.5251（差 0.0755，超過 0.03 警告）。模型包：`bert-macbert-202610280830.zip` size 379935103 sha256 c93e69fa45a3bc121c92b1034f566b18ae544e3ad34efd5bd09be4d56bda43ed；`bert-macbert-202610280830-int8.zip` size 59999755 sha256 a6c6f42c0f4a0460323534601e1de5ffe970bc368db522b003e852cfd2bd28df。對照：先前 ckip（#187 前的舊 notebook，沒打包）驗證 macro-F1 0.6806（epoch 2）
- **設計依據**：`docs/development-spec.md` 7.11（報告寫法）、7.27（流程、int8 與選模型的「自行決定」）；#178
- **相依**：無
- **負責檔案**：
  - `docs/reports/model-evaluation.md`
- **禁區**：只新增一節，不改既有 baseline 內容；不寫人工測試集分數（還沒跑 evaluate，標明「待 evaluate」）；不下切換模型的結論
- **驗收測試**：無
- **驗收條件**：
  - [ ] 新節含：執行環境、資料、訓練設定引用 7.27、各 epoch 表、匯出驗證數字（含 GPU／CPU 診斷證實 #187 的推測）、int8 掉分與依 7.27 的意涵、兩個模型包的檔名／大小／SHA-256、待辦（ckip 用新版重跑、import_model、evaluate）
  - [ ] 註明驗證集 F1 只是訓練切出的 10%，選模型以人工測試集為準
  - [ ] 數字與本派工單背景一致；繁體中文、精簡
- **驗證指令**：`pre-commit run --files docs/reports/model-evaluation.md`
- **回報檔**：`reports/bert-colab-record.json`

## 執行資訊（task.py 產生）

- Issue：#188
- 分支：`docs/bert-colab-record`（從 develop 開出）
- 工作目錄：`.worktrees/bert-colab-record`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
