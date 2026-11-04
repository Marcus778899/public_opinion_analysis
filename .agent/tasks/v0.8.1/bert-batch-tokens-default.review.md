APPROVE 9ed2b93

## 檢查項目

| 項目 | 結果 |
|---|---|
| 負責檔案 | 6 個變更檔都在派工單負責檔案內；`bert-onnx-length-batching` 驗收測試只改 `test_settings_default_max_batch_tokens_is_4096` 一個，且在 qa 的 `test(bert-batch-tokens-default)` commit（bb07baf），worker commit（9ed2b93）沒碰測試 |
| 禁區 | 分批演算法、`load_classifier` 行為未動（只改 `DEFAULT_MAX_BATCH_TOKENS` 常數）；沒碰 `models/`、compose 檔 |
| 條件 1 | `InferenceSettings.max_batch_tokens` 預設 2048（`ge=1` 保留）；`DEFAULT_MAX_BATCH_TOKENS = 2048`，`OnnxClassifier.__init__` 與 `load_classifier` 預設都引用它 |
| 條件 2 | `.env.example` 註解「預設 2048」、`# INFERENCE_MAX_BATCH_TOKENS=2048`，仍是選填註解（D-009） |
| 條件 3 | 7.27 剩下的 4096 都標為「原訂／原 4096」或實測表的不過列；容器實測表三列與 `reports/shadow-memory-measure.json` 一致（qa 已逐項核對） |
| 寫死設定 | 無；程式只有預設值，仍可由環境變數覆蓋（`test_settings_env_overrides_default` 測到） |
| 其他 4096 殘留 | `grep 4096 src infra tests .env.example` 只剩驗收測試裡刻意的覆蓋值與反向斷言 |
| 驗收測試 | 5 個測試分別測 settings 預設、env 覆蓋、常數、`load_classifier` 簽名預設、`.env.example`，對到條件 1、2 |
| 驗證 | 在 worktree 跑 `uv run pytest tests/unit/acceptance/bert-batch-tokens-default tests/unit/acceptance/bert-onnx-length-batching tests/unit/ml -q` → 360 passed；`grep -rn "TODO(bert-batch-tokens-default)" src tests` 沒有結果 |

## 不擋合併的備註

- `docs/development-spec.md` 順序 6 甲方步驟 1：「用預設 2048，與 evaluate 相同」— 順序 3 那次 evaluate（2026-10-28，已打勾）用的是舊預設，而且依 shadow-memory-measure 的結論，當時的舊 image 根本沒用到這個設定；「與 evaluate 相同」容易讓人誤會。之後有 7.27 的文件單時可改成「與容器實測表的 2048 列相同」。
- `docs/security/v0.8.0.md:108` 寫 compose 對 shadow 寫死 4096 的建議（qa 已提）：該檔歸 security，是發版審查的歷史紀錄，不在本單範圍；下次安全審查時更新即可。
