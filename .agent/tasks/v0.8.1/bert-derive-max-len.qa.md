PASS ccfff0e

# bert-derive-max-len 第 2 輪驗證（PR #203）

## 覆蓋率（獨立執行）
指令：`uv run pytest tests/unit/ml/training/test_derive_model.py tests/unit/acceptance/bert-derive-max-len -p no:xdist --cov=radar.ml.training.derive_model --cov-report=term-missing`

```
src/radar/ml/training/derive_model.py      61      1    98%   81
25 passed in 11.36s
```

只跑 `test_derive_model.py`（同程序測試，不含 subprocess 的驗收測試）：15 passed，同樣 98%，只漏第 81 行（`if __name__ == "__main__"` 守衛）。CI 先前列出的 35、60–62、68–77 行都已涵蓋，改到行覆蓋率遠高於 80%。

## 其他檢查
- `uv run pytest tests/unit -q`：1409 passed
- `uv run ruff check .`：All checks passed
- `uv run ruff format --check .`：293 files already formatted
- `grep -rn "TODO(bert-derive-max-len)" src tests`：無結果
- 變更檔：`derive_model.py`、`test_derive_model.py`、驗收測試（檔案與派工單範圍一致）
- 寫死設定值：`derive_model.py` 沒有 port、網址、token；`models/<v>` 只出現在 docstring 用法說明
- 驗收條件（衍生產物與雜湊、三種拒絕、`load_classifier` 以新 `max_len` 截斷）由 9 個驗收測試與 15 個單元測試涵蓋，全部通過

問題數量：0
