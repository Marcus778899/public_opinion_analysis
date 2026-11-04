PASS d535440

# bert-notebook 驗證（PR #166，HEAD d535440）

## 指令與輸出
- `git diff fdc8226 HEAD --stat -- tests/unit/acceptance/bert-notebook` -> 無輸出（驗收測試自 lock fdc8226 後未改動）
- `uv run pytest tests/unit/acceptance/bert-notebook tests/unit/ml/notebook` -> `45 passed in 0.07s`
- `make check` -> ruff check 通過、format 通過（279 files already formatted），`1334 passed in 4.95s`
- `grep -rn "TODO(bert-notebook)" src tests notebooks` -> 只命中驗收測試自己的斷言字串（`assert "TODO(bert-notebook)" not in ...`），notebook 與 src 無

## 驗收條件逐條（讀 notebook 原始碼 + 抽出片段實跑）
1. 無輸出：14 個 cell 的 outputs 皆為空、execution_count 皆為 None；LABELS = positive/negative/neutral 與 `radar.common.enums.Polarity` 順序相同；card 欄位由驗收測試比對，通過。notebook 無 import radar。OK
2. 第一格：BASE 參數與驗證、torch/torchvision/torchaudio/transformers/optimum 釘版本、macbert rev、`CKIP_PR_COMMIT=d3e55b8...`、Google tokenizer rev 8f23c25...（三者與 docs/decisions.md D-025、docs/research/bert-stage8.md 相同）、torch>=2.6 檢查、revision 為 `<` 開頭或非 40 位 hex 即 SystemExit（實跑判斷式：`<revision>` 會停、真 hash 通過）。OK
3. ckip：`use_safetensors=True`；macbert：`use_safetensors=False`（.bin）；兩者 `trust_remote_code=False`。OK
4. 匯出後 logits 最大絕對差 >= 1e-3 raise AssertionError（在打包前）；`Tokenizer.from_file` 重新編碼 ids 與訓練 tokenizer 比對，不一致 raise；int8 另算驗證集 macro-F1，兩個包都產生（符合 7.27 步驟 2，差值印出並寫進 card）；最後一格印各 zip 的 SHA-256。OK
5. 前 50 步後印預估總時間；實跑 `estimate_total_seconds(100,50,1000)=2000.0`、`check_time_budget(11h)` raise 且訊息含 MAX_LEN 與 256、9h 通過；`save_strategy="epoch"`、`get_last_checkpoint` + `resume_from_checkpoint` 可續跑。OK
6. TODO grep 無結果、驗收測試與 make check 通過。OK

## review 要求的修改（7142450 -> d535440）
1. 第一格 pip 同一指令釘 `torchvision==0.22.1`、`torchaudio==2.7.1`（與 torch 2.7.1 配對）；7.27「Colab 套件版本」列已補；新增靜態測試 `test_first_cell_pins_torchvision_and_torchaudio_with_torch`。OK
2. `RUN_NAME = f"{BASE}-len{MAX_LEN}"`，`CKPT_DIR`、`FINAL_DIR`、`WORK` 都帶 RUN_NAME；新增靜態測試 `test_checkpoint_dirs_depend_on_base_and_max_len`。OK
- 不擋合併建議：per_channel=False 與 x86 說明已寫進 7.27 int8 列；下載失敗提示已加進最後一格 markdown。

## 限制
- notebook 與 Colab 套件版本相容性無法在 sandbox 實跑，靜態檢查通過；甲方第一次執行時確認（已寫入 7.27「自行決定」）。
- CI（gitleaks 對驗收測試 GOOGLE_TOKENIZER_REV 誤判，D-026）依指示不列入判定。

問題數量：0
