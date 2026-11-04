APPROVE d535440

# bert-notebook review 第二輪（PR #166，HEAD d535440）

## 上一輪的 2 項（7142450 → d535440）

| # | 問題 | 結果 |
|---|---|---|
| 1 | torch 降版後 torchvision／torchaudio 不配對，`from transformers import Trainer` 失敗 | 已修：第一格同一個 pip 指令釘 `torchvision==0.22.1`、`torchaudio==2.7.1`；7.27「Colab 套件版本」列已補理由；新增靜態測試 `test_first_cell_pins_torchvision_and_torchaudio_with_torch` |
| 2 | 不同 `BASE`／`MAX_LEN` 共用 checkpoint 目錄 | 已修：`RUN_NAME = f"{BASE}-len{MAX_LEN}"`，`CKPT_DIR`、`FINAL_DIR`、`WORK` 都帶它；新增靜態測試 `test_checkpoint_dirs_depend_on_base_and_max_len` |

不擋合併的建議也處理了：`per_channel=False` 與 x86 驗證的說明寫進 7.27 int8 列，最後一格 markdown 加了下載失敗的提示。

## 「第一次在 Colab 跑通」的實測（sandbox 模擬）

- 在 scratch venv 裝第一格的釘選組合（`torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 transformers==4.53.3 optimum[onnxruntime]==1.27.0 scikit-learn tokenizers`）：可以解析（transformers 4.53.3＋tokenizers 0.21.4＋huggingface-hub 0.36.2＋onnxruntime 1.31.0＋accelerate 1.15.0）
- 從 notebook 原始碼逐格 exec，只替換 Colab 專屬的部分：跳過 pip、假 `google.colab.files`（600 筆三類合成資料＋meta）、把 HF id 導向本機的小型隨機 BERT（`macbert` 用只有 `pytorch_model.bin` 的目錄、`ckip` 用只有 `model.safetensors` 的目錄，revision 以外的 kwargs 原樣傳入）、CPU 上 `fp16=False`、`/content/` 換到 scratch。其餘程式碼完全照 notebook
- 兩個 BASE 都跑完全部 7 個 code cell，exit 0：
  - `macbert` 收到 `use_safetensors=False`、`ckip` 收到 `use_safetensors=True`，兩者 `trust_remote_code=False`、revision 正確
  - 第 50 步印出預估時間；`Tokenizer.from_file` 重新編碼 ids 一致；PyTorch 與 ONNX logits 最大差 9e-9；`optimum-cli export`、`ORTQuantizer`（arm64、dynamic）產出 `model_quantized.onnx`；兩個 zip 各只有白名單三個檔
  - 重跑訓練格：`resume from checkpoint: .../checkpoints/macbert-len512/checkpoint-102`，不會讀到另一個 BASE 的目錄
- 產出的 4 個 zip 用本專案的 `import_model.import_model` 匯入、`classifier.load_classifier` 載入並推論（含超過 512 字的輸入）都成功：card 通過 pydantic 驗證、SHA-256 比對通過、`kind=onnx`、`labels` 順序正確
- 沒辦法模擬的部分：Colab 預裝套件與降版之間的互動、GPU／fp16、從 HF 實際下載釘住的 revision（hash 與 D-025、調查一致，上一輪已核對）。7.27 已寫明套件版本「未在 sandbox 驗證、甲方第一次執行時確認」

## 其他檢查

- 負責檔案沒有超出（notebook、`tests/unit/ml/notebook/`、追加一的 `docs/development-spec.md`）；驗收測試目錄只有 qa 的 `fdc8226`
- 7.27 修改（develop...HEAD）：威脅表「預訓練模型的來源」、派工順序第 2 步、已定案表 D-025 列、pickle 那句、已調查的 safetensors 項都改成定案 B，內容與 D-025 一致；`require_primary` 那句沒動；「自行決定」新增 3 列（訓練設定、套件版本、int8 品質）的數值與 notebook 一致；int8「兩個包都產生」與步驟 2 一致
- notebook：14 個 cell 都沒有輸出；沒有 import `radar`；沒有 token、網址、port
- 實際跑過：`uv run pytest tests/unit/acceptance/bert-notebook tests/unit/ml/notebook` → 45 passed；`make check` → 1334 passed；`grep -rn "TODO(bert-notebook)" src tests notebooks` 只命中驗收測試自己的斷言字串
- CI 的 gitleaks 失敗是已知誤判（D-026），依指示不列入判定

## 不擋合併的備註

- 第一格沒有釘 `datasets`（由 `optimum[onnxruntime]` 帶入）。用 uv 在乾淨環境解析時，會選到舊的 `datasets 2.14.4`，搭配新版 pyarrow 會讓 `transformers.trainer` 在 import 時失敗；改裝 `datasets>=3` 就好了。Colab 用 pip，且會保留預裝的 datasets，所以應該不會遇到。甲方第一次執行時如果在 `from transformers import Trainer` 看到 `pyarrow ... PyExtensionType`，就在第一格加上 `"datasets>=3"`
- `optimum-cli export` 讀取 `FINAL_DIR` 時找不到 tokenizer，只會印出警告（`maybe_load_preprocessors` 會 try/except），不影響結果

問題數量：0
