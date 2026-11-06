# 派工單 bert-derive-max-len

- **類型**：feat
- **負責**：backend
- **目標**：新增 `python -m radar.ml.training.derive_model`，從既有模型包產生只改 `max_len` 的衍生版本（例 `bert-ckip-202610280849-len256`），不重訓
- **背景**：shadow（ckip fp32）在容器內被 1.5g cgroup OOM kill（每輪 oom 後 die 137，anon 衝到 1.54 GB；主機 evaluate 只量到 932 MB，低估），依 7.27 順序 6 觀察表「OOM → 回到順序 4」。調查證據：`reports/shadow-restart-investigate.json`。完成後甲方以衍生版本重跑 evaluate
- **設計依據**：`docs/development-spec.md` 7.27「評估結果與進 shadow 的調整」順序表第 4 列與「修正單」表 `bert-derive-max-len` 列（驗收條件以該列為準）、「本節自行決定」的「衍生版本另取 `model_version`」
- **相依**：無
- **負責檔案**：
  - `src/radar/ml/training/derive_model.py`
  - `tests/unit/ml/training/test_derive_model.py`
- **禁區**：不改 `import_model`、`classifier`、模型包格式；不碰 `models/` 實際資料夾（測試用暫存目錄與 `tests/helpers/onnx_model.py`）
- **驗收測試**：
  - `tests/unit/acceptance/bert-derive-max-len/`
- **驗收條件**：
  - [ ] `--model models/<v> --max-len 256` 產生 `models/<v>-len256/`：`model.onnx`、`tokenizer.json` 原樣複製、雜湊不變；card 的 `model_version`、`max_len` 改新值，`params.derived_from` 記原版本，`files` 雜湊仍正確
  - [ ] 目標已存在、`max_len` 不小於原值、新 `model_version` 不符 `import_model` 的格式都拒絕（一行錯誤、非 0 結束碼）
  - [ ] 衍生版本能被 `load_classifier` 載入並以新 `max_len` 截斷
  - [ ] 驗收測試、`make check` 通過；`grep -rn "TODO(bert-derive-max-len)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/bert-derive-max-len tests/unit/ml/training/test_derive_model.py`；`make check`
- **回報檔**：`reports/bert-derive-max-len.json`

## 執行資訊（task.py 產生）

- Issue：#202
- 分支：`feat/bert-derive-max-len`（從 develop 開出）
- 工作目錄：`.worktrees/bert-derive-max-len`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-28

### CI 覆蓋率未過（manager，PR #203 @ 87e44d4）

CI 輸出：
```
錯誤：改到的程式碼覆蓋率 75.4%（61 行），低於 80%：這些行沒有被任何測試執行到
  src/radar/ml/training/derive_model.py：第 35, 60, 61, 62, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 81 行
```

- 驗收測試走 subprocess 呼叫 CLI，覆蓋率量不到；請在 `tests/unit/ml/training/test_derive_model.py` 以同程序方式（直接呼叫 `main()`／函式）補測試涵蓋上列行，不改驗收測試與程式行為
- 補完跑 `make check`，並在本機量改到行的覆蓋率（例：`uv run pytest tests/unit --cov=src/radar/ml/training/derive_model --cov-report=term-missing`）確認 ≥ 80%，輸出附在回報
