PASS 243b510

# QA shadow-missing-model-exit（PR #217，243b510）

## 1. 驗收測試 diff 核對

`git diff develop -- tests/integration/acceptance/bert-shadow-inference/test_shadow_service.py` 只有一行新增，與仲裁指定的內容一致，沒動任何斷言：

```
+    (tmp_path / "model_card.json").write_text(card.model_dump_json(), encoding="utf-8")
```

## 2. CI（本機 GRAFANA_VERSION 打錯，改以 CI 為準）

`gh pr checks 217`（run 40811594103，headSha 243b510c…，conclusion success）：

```
Check	pass	2m0s
Integration Test	pass	3m19s
Security	pass	31s
```

Integration Test log：`uv run pytest tests/unit tests/integration -n auto ... --cov=src/radar` → `1883 passed in 135.92s`，無 failed。先前失敗的 8 個 test_shadow_service 測試包含在內並通過；涵蓋率閘門步驟也通過（job 成功）。

## 3. 本機單元與驗收測試（PYTHONPATH 指向 worktree src，已確認載入 worktree 的 main.py）

- `pytest tests/unit/acceptance/shadow-missing-model-exit tests/unit/ml/inference -q` → 78 passed
- `pytest tests/unit -n 4` → 1522 passed
- `ruff check .` → All checks passed；`ruff format --check .` → 302 files already formatted
- `grep -rn "TODO(shadow-missing-model-exit)" src tests` → 無結果

## 未驗證／備註

- 驗收條件 2 的 `up --wait` 實測依 review 與派工，留給 manager 合併後做（本機 .env 無法 build）；本次不列為 FAIL，因本輪範圍為仲裁後的測試修正與 CI。
