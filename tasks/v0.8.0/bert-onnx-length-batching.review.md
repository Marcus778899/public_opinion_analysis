APPROVE 61ae81b

## 檢查範圍（第 2 輪）

上一輪 APPROVE 7004c5a 的檢查內容不變（程式沒改，`git diff 7004c5a 61ae81b` 只動 1 個測試檔）；本輪只看新 commit 61ae81b，對照派工單「追加 2026-10-28」的範圍更新、qa 證據（PASS 61ae81b）、worker 回報。

| 項目 | 結果 |
|---|---|
| 改動者與範圍 | 61ae81b 是 qa 的 `test(bert-onnx-length-batching)` commit，只改 `tests/integration/acceptance/bert-shadow-inference/test_shadow_service.py`，符合追加的「只由 qa 修改」 |
| 修改內容 | `env` fixture 的 fake 改成 `lambda model_dir, *, threads, max_batch_tokens`（keyword-only，與 `load_classifier` 簽名一致，正是 CI 的 `TypeError` 根因）；`test_shadow_role_uses_classifier_with_inference_threads` 加 `INFERENCE_MAX_BATCH_TOKENS=3000` 並斷言傳入值為 3000；其他斷言未動 |
| 是否真的測到驗收條件 | 新斷言驗證 inference `main()` 把 `settings.max_batch_tokens` 傳進 `load_classifier`（設非預設值 3000，不會被預設 4096 蒙混過關）；evaluate 的 `main()` 傳入已由單元驗收測試涵蓋 |
| 其他 fake | 全 repo `load_classifier` 的替身只剩 `bert-evaluate-report-fix` 的 `fake_load(*_a, **_k)`，可吃新 keyword，不受影響 |
| worker 回報 | `files_changed` 與負責檔案一致；驗證含整合測試 `361 passed`（HEAD 61ae81b，已 `down -v`） |

實際執行（worktree，HEAD 61ae81b）：`uv run pytest -q tests/unit/acceptance/bert-onnx-length-batching tests/unit/acceptance/bert-classifier tests/unit/acceptance/bert-evaluate-report-fix tests/unit/ml` → `367 passed in 1.63s`。整合測試未自行重跑，依 qa 與 worker 各自實跑的 `361 passed`；PR CI 的 Integration Test 在 review 時仍 pending，合併前需確認轉綠。

## 非阻擋備註

- 上一輪的 `no_padding()` 防呆建議仍適用（見前版說明），不阻擋本 PR。
