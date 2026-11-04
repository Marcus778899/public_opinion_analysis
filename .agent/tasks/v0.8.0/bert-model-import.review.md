APPROVE 16d7c02

# Review：PR #160 bert-model-import（HEAD 16d7c02）

## 檢查範圍

| 項目 | 結果 |
|---|---|
| 變更檔案 | `src/radar/ml/training/import_model.py`、`tests/unit/ml/training/test_import_model.py`（worker，fbdab12）；`tests/unit/acceptance/bert-model-import/`（qa 42f8b4e、依仲裁修正 16d7c02，已重新 lock）。沒有改到負責檔案以外 |
| 骨架簽名與禁區 | `import_model(zip_path, models_dir) -> Path`、`ALLOWED_FILES`、`MAX_TOTAL_BYTES`、`MODEL_VERSION_RE`、兩個例外類別、`main()` 與骨架一致；`ModelCard`、helper 未改；`tests/unit/ml/test_stage8_interfaces.py` 通過 |
| 7.27 模型包格式 | 白名單三檔 `model.onnx`、`tokenizer.json`、`model_card.json`；card 以 `ModelCard.model_validate_json` 驗證（含 `labels` 三個 Polarity、onnx 需 `max_len`／`files`）；不接受 pickle 類格式 |
| 7.27 威脅與對策：推論主機 | 先比對 `card.files` 的 SHA-256（`model.onnx`、`tokenizer.json`，缺雜湊項也拒絕）才寫檔 |
| 7.27 威脅與對策：本機檔案系統 | 成員名稱須逐字等於白名單（路徑、目錄項、多餘、缺少、重複都拒絕），寫入用白名單檔名不依 zip 路徑；大小以實際讀出位元組累計，上限 2 GB；`model_version` 用 `fullmatch`（`\n` 結尾也擋）且在組路徑前檢查；目標已存在丟 `ModelExistsError` |
| 不留半套資料夾 | 驗證全在記憶體完成後才在 `models_dir` 內建 staging，寫完同一檔案系統 `rename`；寫入失敗刪 staging（有單元測試） |
| 寫死設定 | 無；`MODELS_DIR` 沿用 `train.py` 既有常數，與 baseline 一致 |
| 程式碼規範 | log 用 `radar.common.log`；入口 `setup_logging` + `log.catch`；type hints 齊全；註解在 3 行內 |
| 測試是否測到驗收條件 | 驗收測試涵蓋雜湊不符（兩檔各一）且無殘留、多餘／缺少檔、路徑穿越（多種）、超過上限與上限內、上限常數、非法 `model_version`（含空字串，已依仲裁修正）與 64 字元、目標已存在且原資料不動、card 非 JSON；worker 單元測試補非 zip、重複成員、card 缺雜湊項、card 為陣列、schema 不符、寫入失敗清 staging |
| 驗證 | 自行執行 `uv run pytest tests/unit/acceptance/bert-model-import tests/unit/ml/training/test_import_model.py tests/unit/ml/test_stage8_interfaces.py -q` → 53 passed；`grep -rn "TODO(bert-model-import)" src tests` 無結果；`gh pr checks 160`：Check、Integration Test、Security 全 pass |

## 非阻擋建議（不影響本次結論，可之後開單）

1. `import_model.py:72` — card 的 `kind` 沒有限定 `onnx`：`kind=sklearn` 且 `files` 有正確雜湊的包會被匯入，之後 `load_classifier` 找不到 `model.joblib` 而失敗。不構成安全問題（白名單擋掉 joblib），但在匯入時拒絕較早給出錯誤。
2. `import_model.py:47` — 加密成員或不支援的壓縮法會丟 `RuntimeError`／`NotImplementedError` 而不是 `ModelPackageError`；CLI 有 `log.catch`，只是錯誤訊息較不直接。
3. `_read_members` 最多把 2 GB 讀進記憶體（qa 觀察已列）；規格上限內，單人本機 CLI 可接受。
