# 派工單 ml-cli-usability

- **類型**：fix
- **負責**：backend
- **目標**：`evaluate`、`compare`、`cross_check` 指令列的錯誤提示、`--help` 說明與 CSV 輸出安全（#173 evaluate 部分、#174 evaluate／compare 部分、#175、#176、#168）
- **背景**：UAT v0.8.0 F-3～F-5（docs/uat/v0.8.0.md）、資安 v0.8.0 L-1（docs/security/v0.8.0.md）、compare review 非阻擋建議（reports/bert-compare.review.md）；細節見各 issue。import_model 的部分另開單
- **設計依據**：上列 issue；`docs/development-spec.md` 7.27（compare、evaluate 的輸出）；共用函式放哪由 worker 決定（不可放進 `common/settings.py`）；model_version 格式從 import_model 的 `MODEL_VERSION_RE` import，不改 import_model
- **相依**：無
- **負責檔案**：
  - `src/radar/ml/training/evaluate.py`
  - `src/radar/ml/training/compare.py`
  - `src/radar/ml/labeling/cross_check.py`
  - 新增的共用模組（例 `src/radar/common/cli.py`、`src/radar/common/csv_safe.py`）
  - `tests/unit/ml/training/test_evaluate.py`、`tests/unit/ml/training/test_compare.py`、`tests/unit/ml/labeling/`、共用模組的單元測試
  - `tests/unit/acceptance/ml-cli-usability/`
- **禁區**：不改 import_model、settings、評估與比較的計算邏輯（#168 的取列修正除外）、輸出格式欄位
- **驗收測試**：
  - `tests/unit/acceptance/ml-cli-usability/`
- **驗收條件**：
  - [ ] evaluate：模型資料夾不存在、不是模型包時印一行說明、非 0 結束碼、沒有 traceback（#173）
  - [ ] evaluate、compare、cross_check：缺 ClickHouse 環境變數時印出缺哪幾個變數名稱與「用 `uv run --env-file .env`」提示、非 0 結束碼、沒有 traceback（#175）
  - [ ] evaluate、compare 的 `--help` 每個參數都有說明；`--since` 有 ISO 範例與時區說明（#174）
  - [ ] CSV：以 `=` `+` `-` `@` Tab CR 開頭的字串欄位前置 `'`，其他不變；compare disagreements 與 cross_check 兩處用同一函式（#176）
  - [ ] compare：`--a`／`--b` 格式不符時拒絕；同一篇同一 `predicted_at` 多筆時 polarity 與 score 來自同一列（#168）
  - [ ] 驗收測試、`make check` 通過；`grep -rn "TODO(ml-cli-usability)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/ml-cli-usability tests/unit/ml`；`make check`
- **回報檔**：`reports/ml-cli-usability.json`

## 執行資訊（task.py 產生）

- Issue：#214
- 分支：`fix/ml-cli-usability`（從 develop 開出）
- 工作目錄：`.worktrees/ml-cli-usability`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
