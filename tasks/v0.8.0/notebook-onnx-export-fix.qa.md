PASS b1b812f

# notebook-onnx-export-fix 驗證（fast 通道，PR #183）

## 驗收條件
1. 第一格處理 diffusers import 錯誤：通過（靜態檢查）。diff 在第一格 `pip install` 之後、`import torch` 之前加 `pip uninstall -y -q diffusers`；只移除、不新增套件。已讀 diff，未動訓練參數、revision、模型包格式、驗證門檻、`src/`。
2. 單元測試鎖住：通過。新增 `test_first_cell_uninstalls_diffusers_after_installing_packages`（檢查指令存在，且順序為 install、uninstall、import torch）與 `test_notebook_has_no_outputs`。
3. notebook 無輸出、`make check`：通過。

## 實際執行
- `uv run pytest tests/unit/ml/notebook`：17 passed in 0.14s
- `uv run pytest tests/unit`（make check 的測試部分）：1350 passed in 4.29s
- `uv run ruff check .`：All checks passed
- `pre-commit run --all-files`：trim whitespace、end of files、check yaml、ruff、ruff format、bandit 全部 Passed
- 程式檢查 notebook JSON：所有 code cell 的 outputs 為空、execution_count 為 null

## 邊界情況
- diffusers 未安裝時：`pip uninstall -y` 對不存在的套件只印 Skipping 警告。我用不存在的套件名試過，pip 本身沒有報錯。該次指令的 rc=1 來自本機 pyenv rehash 無法寫入（sandbox 限制），與 pip 無關。所以 `check=True` 不會讓第一格失敗。
- 寫死設定值：此變更沒有新增 port、網址或 token。

## 未驗項目（沒有真實 Colab）
- 未實跑 notebook。uninstall diffusers 後，「4. 匯出 ONNX」的 `optimum-cli export onnx` 是否成功，需甲方在 Colab 實跑確認。
- 第 5 部分 `optimum.onnxruntime` 在 uninstall 後是否正常，也未驗證。worker 回報也列為待驗。
- Colab 預裝的其他套件，是否也因 huggingface_hub 版本衝突而失敗，未驗證。
- 已跑過舊版第一格的工作階段，需重新啟動執行階段後從第一格重跑。這點來自 worker 說明，我沒有實測。
