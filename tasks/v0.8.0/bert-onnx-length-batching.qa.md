PASS 61ae81b

# QA bert-onnx-length-batching（第 2 輪，PR #197）

## 執行結果（自己實際執行）

- `uv run pytest tests/unit -q`（worktree）：`1384 passed in 4.65s`（含 tests/unit/acceptance/bert-onnx-length-batching、bert-classifier、tests/unit/ml）
- `uv run ruff check .`：`All checks passed!`；`uv run ruff format --check .`：`290 files already formatted`
- `grep -rn "TODO(bert-onnx-length-batching)" src tests`：無結果
- 整合測試 `docker compose --env-file .env -f .worktrees/bert-onnx-length-batching/compose.yaml run --rm test`：`======================== 361 passed in 63.64s (0:01:03) ========================`，含 `tests/integration/acceptance/bert-shadow-inference/test_shadow_service.py` 全部（上輪失敗的 10 個）。
- 已執行 `... down -v`，容器、網路、volume 全部移除。

## 驗收條件對照

1. 分小批與整批機率差 < 1e-5、順序一致：`_chunks`／`predict_proba` 以排序索引回填 results；驗收測試通過。
2. 每次 run 篇數 × 序列長度 ≤ 上限：`_chunks` 以 (篇數+1) × 該篇長度判斷（遞增排序，該篇即最長）；上限 ≥ max_len 且輸入已截斷，故單篇不會超過上限；驗收測試通過。
3. `InferenceSettings.max_batch_tokens` 預設 4096；`OnnxClassifier` 在 < max_len 時 raise ValueError；`load_classifier` keyword-only `max_batch_tokens`；inference 與 evaluate 的 `main()` 皆傳入 `settings.max_batch_tokens`（diff 已確認）。
4. 驗收測試、make check 等價項（unit+ruff）通過；無殘留 TODO。

## 其他檢查

- 上輪整合測試失敗根因（fake lambda 不接受 `max_batch_tokens`）已由 commit 61ae81b 修正，並新增驗證 `INFERENCE_MAX_BATCH_TOKENS=3000` 傳入 `load_classifier`；只動該檔的 fake 與傳入驗證。
- `.env.example` 以註解寫選填（符合 D-009）。
- 寫死的設定值：只有規格指定預設 4096；無 port、網址、token。
- 邊界：空輸入回傳 []、空文本寬度以 max(...,1) 處理。
- 未實測：ckip fp32 真實耗時與 RSS（派工單明載待甲方重跑 evaluate，不屬本單驗收）。

問題數量：0
