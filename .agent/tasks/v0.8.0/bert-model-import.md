# 派工單 bert-model-import

- **類型**：feat
- **負責**：backend
- **目標**：`python -m radar.ml.training.import_model --zip <路徑>` 把模型包安全解到 `models/<model_version>/`
- **背景**：階段 8（D-019、D-020）。骨架已由 `bert-skeleton`（PR #156）建好；測試用模型包 zip 用 `tests/helpers/onnx_model.py`（只呼叫、不修改）
- **設計依據**：`docs/development-spec.md` 7.27「模型包格式」「威脅與對策」（本機檔案系統、推論主機兩列）「測試」
- **相依**：bert-skeleton（已合併）
- **負責檔案**：
  - `src/radar/ml/training/import_model.py`
  - `tests/unit/ml/training/test_import_model.py`
- **禁區**：不改骨架的簽名與 `ModelCard`（要改先回報 manager）；不改 helper 與驗收測試；不接受任何 pickle 類格式
- **驗收測試**：`tests/unit/acceptance/bert-model-import/`
- **驗收條件**：
  - [ ] 比對 `model_card.files` 的 SHA-256，不符就拒絕且不留下半套資料夾
  - [ ] 只解出白名單三個檔名、不依 zip 內路徑；多餘檔名、路徑穿越、解壓總大小超過 2 GB、`model_version` 不符 `^[a-z0-9][a-z0-9-]{0,63}$`、目標已存在都拒絕
  - [ ] `grep -rn "TODO(bert-model-import)" src tests` 沒有結果
  - [ ] 驗收測試與 `make check` 通過；PR 的 CI 全綠
- **驗證指令**：`uv run pytest tests/unit/acceptance/bert-model-import tests/unit/ml/training/test_import_model.py`；`make check`
- **回報檔**：`reports/bert-model-import.json`

## 執行資訊（task.py 產生）

- Issue：#158
- 分支：`feat/bert-model-import`（從 develop 開出）
- 工作目錄：`.worktrees/bert-model-import`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
