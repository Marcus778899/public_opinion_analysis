PASS 9ed2b93

## 驗證（worktree .worktrees/bert-batch-tokens-default，PR #206）

1. 預設值（條件 1）：diff 顯示 `settings.py` max_batch_tokens 與 `classifier.py` DEFAULT_MAX_BATCH_TOKENS 皆 4096→2048；驗收測試通過。
2. `.env.example`（條件 2）：註解與範例值皆 2048。
3. 開發規格 7.27（條件 3）：`grep -n 4096 docs/development-spec.md` 只剩 1450（說明「原訂」）、1479（容器實測表 4096 列，標不過）、1505（「原 4096」）、1517（「原訂」）；順序 3 的步驟 1 已改為預設 2048。無任何一處把 4096 寫成預設。
4. 容器內實測表與 reports/shadow-memory-measure.json（512 版）逐項核對一致：4096＝1268 MB／27.8／34.5 s／0.612；2048＝997 MB／23.8／30.5 s／0.612；1024＝951 MB／21.5／28.7 s／0.612。
5. 指令輸出：
   - `uv run pytest tests/unit/acceptance/bert-batch-tokens-default tests/unit/acceptance/bert-onnx-length-batching tests/unit/ml -q` → 360 passed
   - `uv run pytest tests/unit -q` → 1414 passed
   - `ruff check .` All checks passed；`ruff format --check .` 294 files already formatted；`pre-commit run --all-files` 全 Passed
   - `grep -rn "TODO(bert-batch-tokens-default)" src tests` → 無結果
6. 範圍：變更檔僅在負責檔案內（另有 bert-onnx-length-batching 驗收測試一個測試由 2048 修正，派工單允許）。

## 備註（非 FAIL）
- docs/security/v0.8.0.md:108 建議「compose 對 shadow 寫死 4096」，與新預設不一致；該檔不在本單負責範圍，屬安全審查歷史紀錄，建議 manager 後續留意。
