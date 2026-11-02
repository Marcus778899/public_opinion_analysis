# 派工單 bert-notebook

- **類型**：feat
- **負責**：backend
- **目標**：`notebooks/bert_finetune.ipynb`：甲方在 Colab 依第一格參數 `BASE`（`macbert`｜`ckip`）fine-tune 一個預訓練模型，匯出 ONNX、產生 fp32 與 int8 兩個模型包並印出 SHA-256；加上 notebook 的靜態單元測試
- **背景**：階段 8 S8-01（D-019：agent 備 notebook，甲方在 Colab 跑）。D-021 兩個預訓練模型各訓一版；D-022 notebook 端套件 `torch`、`transformers`、`optimum[onnxruntime]`（第一格釘版本，不進 `uv.lock`）；D-024 訓練資料只在工作階段上傳、不放 Drive。D-025 定案 B：
  - `ckip`：權重改釘 `ckiplab/bert-base-chinese` 的 safetensors 轉換 PR（`refs/pr/1`，commit `d3e55b839fccbf1bba9e194b8626b18b30fcc5f3`），只載 safetensors（`use_safetensors=True`）；tokenizer 照 7.27 用 `google-bert/bert-base-chinese`（釘 revision）
  - `macbert`：沒有 safetensors，載 `.bin`；第一格檢查 `torch>=2.6`（weights_only 預設）不符就停止
  - 兩者都釘 revision（值見 `docs/research/bert-stage8.md`「模型 revision」與末節）、`trust_remote_code=False`；`base_model` 與 tokenizer 來源都連同 revision 記進 `model_card`
- **設計依據**：`docs/development-spec.md` 7.27「流程與交付物」步驟 2、「模型包格式」、匯出與 tokenizer 段、「測試」、「威脅與對策」、「自行決定」（`max_len`、驗證集、Colab 12 小時上限、`model_version` 命名）；`docs/decisions.md` D-021、D-022、D-024、D-025
- **相依**：bert-skeleton（已合併）
- **負責檔案**：
  - `notebooks/bert_finetune.ipynb`
  - `tests/unit/ml/notebook/`
- **禁區**：notebook 內不 import `radar`；進 git 不帶輸出；不改 `src/`、helper、驗收測試；不放 token 或任何設定值；開發規格 7.27 的 D-025 同步由 manager 之後另行追加（目前開發規格屬於進行中的 bert-classifier），先不要改
- **驗收測試**：`tests/unit/acceptance/bert-notebook/`
- **驗收條件**：
  - [ ] notebook 沒有輸出；類別順序與 `model_card` 欄位與 `radar` 的定義一致（單元測試比對 notebook 原始碼）
  - [ ] 第一格：`BASE` 參數、套件版本、revision（含 `ckip` 的 safetensors PR commit 與 Google tokenizer）、`torch>=2.6` 檢查、revision 仍是佔位字串時停止
  - [ ] `ckip` 只載 safetensors、`macbert` 載 `.bin`，兩者 `trust_remote_code=False`
  - [ ] 匯出後比對 PyTorch 與 ONNX logits（最大絕對差 < 1e-3）、`tokenizers.Tokenizer.from_file` 重新編碼的 ids 與訓練用一致、int8 另比對驗證集 macro-F1，通過才打包；最後一格印出各檔 SHA-256
  - [ ] 前 50 步後印預估總時間，超過 10 小時停止並提示 `max_len` 256；每個 epoch 存 checkpoint、可續跑
  - [ ] `grep -rn "TODO(bert-notebook)" src tests notebooks` 沒有結果；驗收測試與 `make check` 通過
- **驗證指令**：`uv run pytest tests/unit/acceptance/bert-notebook tests/unit/ml/notebook`；`make check`
- **回報檔**：`reports/bert-notebook.json`

## 執行資訊（task.py 產生）

- Issue：#163
- 分支：`feat/bert-notebook`（從 develop 開出）
- 工作目錄：`.worktrees/bert-notebook`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-22

### 負責檔案更新（manager，取代原欄位：同一個 PR 內同步 D-025 到 7.27）

- **負責檔案**：
  - `notebooks/bert_finetune.ipynb`
  - `tests/unit/ml/notebook/`
  - `docs/development-spec.md`

### 要做的事

- bert-classifier 已合併，開發規格可以改了；原「禁區」中「開發規格 7.27 的 D-025 同步先不要改」這句作廢
- 把 7.27 裡 D-025 還寫成「待決定」的地方改成定案 B（威脅表「預訓練模型的來源」列、派工順序第 2 步、「已定案」表後那句 pickle 說明、「已調查」的 safetensors 轉換 PR 項）；「已定案」表加一列 D-025；只改這幾處（同節 `require_primary` 那句由 bert-shadow-inference 改，不要動）
- 開工前先把 develop 最新內容同步進來的事由 manager 處理；你只在自己的 worktree 改

## 追加 2026-10-22

### 實作中的新決定要回寫（manager）

- 回報裡自行決定的訓練設定（3 個 epoch、learning rate 2e-5、有效 batch 16、class weight balanced、Colab 端三個套件的釘選版本）寫進 7.27「自行決定」表，並註明套件版本未在 sandbox 驗證、甲方第一次執行時確認
- 「int8 驗證集 macro-F1 比 fp32 低超過 0.03 就只跳過 int8 包」與 7.27 流程步驟 2「每次執行兩個模型包」、「自行決定」的「fp32 或 int8 進 shadow」（由人工測試集決定）不一致：照 7.27 的現行設計改回每次都產生兩個包（int8 比對結果印出、寫進 card 或輸出即可），或在回報說明為何必須偏離，由 review 判斷；不要自己改 7.27 的那兩處設計
- 分支已由 manager `pr.py sync` 到最新 develop（2c5c0b5），先確認 7.27 合併後內容正確
- 重跑驗收測試與 `make check`，更新 `reports/bert-notebook.json`

## 追加 2026-10-22

### reports/bert-notebook.review.md

REQUEST_CHANGES 7142450

# bert-notebook review（PR #166）

## 檢查範圍

- `gh pr diff 166`：`notebooks/bert_finetune.ipynb`、`tests/unit/ml/notebook/`、`docs/development-spec.md`（7.27）；`tests/unit/acceptance/bert-notebook/` 只有 qa 的 `fdc8226 test(bert-notebook)`，worker 沒改
- 負責檔案：沒有超出（含追加一的 `docs/development-spec.md`）；notebook 沒有 import `radar`、沒有 token／網址／port，所有 cell 沒有輸出
- 實際跑過：`uv run pytest tests/unit/acceptance/bert-notebook tests/unit/ml/notebook` → 43 passed；`grep -rn "TODO(bert-notebook)"` 只命中驗收測試自己的斷言字串
- 套件相容性：下載 `transformers 4.53.3`、`optimum 1.27.0` 的 wheel 與 PyPI metadata 對照原始碼
  - `optimum[onnxruntime]==1.27.0` 要求 `transformers>=4.36,<4.54` → 4.53.3 相容；`transformers 4.53.3` 要求 `tokenizers>=0.21,<0.22`，pip 會一起解析，不衝突
  - `check_torch_load_is_safe()` 要求 torch>=2.6 才能載 `.bin`，與第一格的檢查一致
  - `use_safetensors=True` 且 `revision` 不是 `main` 時，找不到 safetensors 直接 `OSError`，不會改走 auto_conversion 或改載 `.bin` → `ckip` 只載 safetensors 成立
  - `AutoQuantizationConfig.arm64(is_static, ..., per_channel)`、`ORTQuantizer.from_pretrained(path, file_name=)`、`quantize(save_dir=, quantization_config=)` 簽名正確；輸出檔名 `<stem>_quantized.onnx` → `model_quantized.onnx` 正確
- 兩個 tokenizer：都以 `BertTokenizerFast.from_pretrained(id, revision=)` 載入；`macbert` 用自己 repo 與同一個 revision，`ckip` 用 `google-bert/bert-base-chinese@GOOGLE_TOKENIZER_REV`；`save_pretrained` 會寫出 `tokenizer.json`；以 `Tokenizer.from_file` 重新編碼比對 ids，與 `classifier.OnnxClassifier` 的載入方式一致
- D-025 B：revision 與 `docs/decisions.md` D-025、調查的 hash 相同；兩者都設 `trust_remote_code=False`；card 的 `base_model` 與 `params.tokenizer` 都是 `<id>@<rev>`
- 模型包與 `import_model`／`classifier` 的介面（7.27「模型包格式」）：zip 只有白名單三個檔；`files` 的 SHA-256 在複製後才計算；`model_version` 符合 `MODEL_VERSION_RE`；`params` 值都是 str／int／float；`labels` 與 `Polarity` 順序相同；`kind=onnx`、`max_len` 有值；ONNX 輸出 `logits`，輸入有 `token_type_ids` 時補 0，與 `OnnxClassifier` 一致；`[PAD]` padding 與推論端一致
- 匯出驗證：logits 最大絕對差 >= 1e-3 時 AssertionError，順序在打包前；int8 一律打包、印出 macro-F1 差值並寫進 card，符合追加二與 7.27 步驟 2
- 7.27 同步：威脅表、派工順序第 2 步、已定案表 D-025 列、pickle 那句、已調查項的內容都與 D-025 一致；`require_primary` 那句沒動；「自行決定」新增三列的數值與 notebook 相同，也寫了「未在 sandbox 驗證」

## 要修改的問題

1. `notebooks/bert_finetune.ipynb:38`（第一格 pip install）— Colab 第一次執行時 `from transformers import Trainer` 幾乎一定會失敗。原因：Colab 預先裝了 torchvision、torchaudio，版本與內建的 torch（2.8 以後）配對；把 torch 降到 2.7.1 以後，torchvision 的 C 擴充載不起來，import torchvision 時丟出 `operator torchvision::nms does not exist`。`transformers 4.53.3` 的 `trainer.py:64` 會 import `image_processing_utils`，裡面的 `image_utils.py:58-59` 只要偵測到 torchvision 有安裝就會 `from torchvision.transforms import InterpolationMode`，所以第五格一定會撞到 — 改法：在同一個 pip 指令裡釘上配對版本 `torchvision==0.22.1`、`torchaudio==2.7.1`（或在 install 之前先 `pip uninstall -y torchvision torchaudio`）；7.27「自行決定」的「Colab 套件版本」列補上這一點；在 `tests/unit/ml/notebook/` 加一個靜態測試：第一格有釘 torch 的話，也要釘 torchvision（或有 uninstall）
2. `notebooks/bert_finetune.ipynb:288`、`:319`（`CKPT_DIR = "/content/checkpoints"`、`get_last_checkpoint(CKPT_DIR)`）— 不同的 `BASE`、`MAX_LEN` 共用同一個 checkpoint 目錄。7.27 步驟 2 要求兩個 BASE 各跑一次，甲方在同一個工作階段改 `BASE=ckip` 重跑時，會讀到 macbert 最後一個 checkpoint，把它的權重與 trainer state（global_step 已經到最後）載進 ckip 模型，等於沒有訓練就打包，card 上卻寫 `base_model=ckiplab/...`，而且不會出現任何錯誤。改 `MAX_LEN` 256 後重跑也一樣，會從 512 的 checkpoint 接著訓練 — 改法：目錄名稱加上 `BASE` 與 `MAX_LEN`，例如 `f"/content/checkpoints/{BASE}-len{MAX_LEN}"`（`FINAL_DIR` 照同樣方式改）；加一個靜態測試確認 `CKPT_DIR` 的值有用到 `BASE` 與 `MAX_LEN`

## 不擋合併的建議（可以一起改，或記進回報）

- 第 9 格的 `per_channel=False` 不是 `arm64()` 的預設值（預設是 True），可以補進 7.27「自行決定」的 int8 那一列
- int8 的驗證集 F1 是在 Colab 的 x86 CPU 上算的。arm64 config 用 U8S8，在沒有 VNNI 的 x86 上可能飽和，算出來的 F1 會比在 arm64 上低；只會多印一行警告，最後還是看步驟 4 在本機的評估，不影響結論
- `macbert` 走 `.bin` 時，transformers 會在背景開一個 auto_conversion thread，去呼叫 HF 的轉換服務（`ignore_errors=True`），這是對外的請求，不影響載入的權重
- 第 13 格用 `files.download` 下載約 400 MB 的 fp32 包，在 Colab 偶爾會中斷；markdown 可以補一句「失敗時從左側檔案面板下載 `/content/packages/`」
- notebook 端的 tokenizers 是 0.21.x，本機是 0.23.3；推論端讀舊版產生的 `tokenizer.json` 應該相容，甲方第一次匯入後跑 `evaluate` 就能確認

問題數量：2
