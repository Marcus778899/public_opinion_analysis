# 派工單 notebook-onnx-export-fix

- **類型**：fix
- **負責**：backend
- **通道**：fast
- **目標**：`notebooks/bert_finetune.ipynb` 在現行 Colab（Python 3.13）上能從 fine-tune 一路跑到匯出 ONNX、量化、打包，不再因 diffusers 中斷
- **背景**：甲方 2026-10-28 在 Colab 以 `BASE = "ckip"` 跑：fine-tune 成功，「4. 匯出 ONNX」的 `optimum-cli export onnx` 回傳 1。實際錯誤：optimum `exporters/tasks.py` 第 54 行 `from diffusers import DiffusionPipeline` → Colab 預裝的 diffusers 從 `huggingface_hub` import `resolve_revision` 失敗（`ImportError`），版本與第一格釘的 transformers 4.53.3 帶進來的 huggingface_hub 不相容。第 5 部分的 `optimum.onnxruntime` 很可能也會被同一個問題擋住。甲方暫時用 `pip uninstall -y diffusers` 繞過（manager 提供，結果待回報）。不可新增套件（決策分級②，D-022 的三個套件以外要先問甲方）
- **設計依據**：`docs/development-spec.md` 7.27（Colab 端套件、匯出流程）；`docs/decisions.md` D-022
- **相依**：無
- **負責檔案**：
  - `notebooks/bert_finetune.ipynb`
  - `tests/unit/ml/notebook/`
- **禁區**：不改訓練參數、revision、模型包格式與驗證門檻；notebook 進 git 不帶輸出；不新增套件；不改 `src/`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 第一格處理掉 Colab 預裝套件造成的這個 import 錯誤（做法自定，回報說明理由與是否需要重新啟動執行階段）；若第一格提示文字或 README 用語需改，在回報列出，由 manager 改 README
  - [ ] 補單元測試（靜態比對 notebook 原始碼）鎖住這個處理，避免回歸
  - [ ] notebook 無輸出；`make check` 通過
- **驗證指令**：`uv run pytest tests/unit/ml/notebook`；`make check`
- **回報檔**：`reports/notebook-onnx-export-fix.json`

## 執行資訊（task.py 產生）

- Issue：#182
- 分支：`fix/notebook-onnx-export-fix`（從 develop 開出）
- 工作目錄：`.worktrees/notebook-onnx-export-fix`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
