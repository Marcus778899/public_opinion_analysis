APPROVE b1b812f

# notebook-onnx-export-fix review（PR #183，fast 通道）

## 檢查項目

| 項目 | 結果 |
|---|---|
| 改動範圍 | 只有 `notebooks/bert_finetune.ipynb`、`tests/unit/ml/notebook/test_notebook_cells.py`，都在負責檔案內；沒有動 `src/` |
| 禁區 | 訓練參數、revision、模型包格式、驗證門檻都沒動；沒有新增套件，只移除 Colab 預裝的 diffusers（D-022 範圍內） |
| 驗收 1：第一格處理 import 錯誤 | `pip install` 之後、`import torch` 之前加 `pip uninstall -y -q diffusers`，`check=True`。diffusers 沒裝時 pip 只會印 Skipping 警告，exit code 是 0，所以不會讓第一格失敗。optimum `exporters/tasks.py` 會 import diffusers，移除之後匯出時就不會碰到不相容的 huggingface_hub。NOTE 註解 2 行，符合規範 |
| 驗收 2：單元測試鎖住 | `test_first_cell_uninstalls_diffusers_after_installing_packages` 檢查指令存在，也檢查順序是 install、uninstall、import torch，能抓到這行被刪掉或移位的回歸；`test_notebook_has_no_outputs` 鎖住「不帶輸出」 |
| 驗收 3：無輸出、`make check` | 我在 worktree 實跑 `uv run pytest -q tests/unit/ml/notebook`，17 passed；qa 已跑 `make check` 對應項目，全過 |
| 寫死設定、安全 | 沒有新增設定值；subprocess 用 list 參數，沒有字串拼接 |

## 非阻擋事項（給 manager）

- 文件同步：開發規格 7.27 的「Colab 套件版本」列（`docs/development-spec.md:1384`）和風險表（`:1416`）沒有提到第一格會移除 diffusers。worker 不負責 docs，建議 manager 在該列補一句「第一格移除 Colab 預裝的 diffusers（與釘版的 huggingface_hub 不相容，optimum 匯出時會 import）」。要不要改 README 第 70 行，照 worker 的 open_questions，由 manager 決定。
- 真實 Colab 還沒驗證，包括第 5 部分 `optimum.onnxruntime`，要等甲方實跑回報（#178 追蹤）。
