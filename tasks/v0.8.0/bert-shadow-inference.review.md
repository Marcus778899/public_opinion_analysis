APPROVE a8f1d2c

# Review PR #165（bert-shadow-inference）

依據：派工單（含 2026-10-22 追加）、開發規格 7.27「shadow 並行」「載入」「測試」「威脅與對策」、設計文件 8.4、CLAUDE.md 程式碼與測試規範。CI（Check、Integration Test、Security）全綠。

## 檢查項目

| 項目 | 結果 |
|---|---|
| 負責檔案 | 改動都在負責檔案內：`main.py`、`tests/unit/ml/inference/test_main.py`、`tests/integration/conftest.py`、`test_inference_consumer.py`、`test_inference_shadow.py`、`docs/development-spec.md`；驗收測試目錄只有 qa 的 `0f4b100 test(bert-shadow-inference)`；禁區 `roles.py`、`settings.py`、`classifier.py`、`test_roles.py` 未動 |
| group／topic／表 | 全由 `ROLE_TARGETS[settings.role]` 與 `consumer_group()` 取得，無寫死；`INFERENCE_ROLE` 是列舉，查表不會 KeyError |
| primary 行為不變 | group 仍為 `PRIMARY_GROUP = "inference"`（DLQ 來源名稱同）；topic `names.PREDICTIONS`；快取表 `predictions`（`load_cache` 預設值）；`Prediction` 欄位與 flush 後才更新快取的順序未變；`top_class` 以 `Polarity` 宣告順序取 max，與舊 `predict()` 在 `dict.fromkeys(Polarity)` 上取 max 的同分規則相同 |
| `top_class` 缺類 KeyError | 正式路徑不會發生：`SklearnClassifier` 以 `dict.fromkeys(Polarity, 0.0)` 補齊三類；`OnnxClassifier` 依 `card.labels` 建 dict，`ModelCard._labels_are_three_polarities` 驗證 labels 恰為三個 `Polarity`，logits 欄數不符時 `zip(strict=True)` 拋 ValueError（往上拋、不 commit，與舊行為同）。移除舊的缺類單元測試合理（邏輯已搬到 `SklearnClassifier`，屬 bert-classifier 的測試範圍） |
| 處理完才 commit／DLQ／冪等 | `BatchConsumer` 與 `DlqPublisher` 用法不變，只換 group；模型錯誤往上拋（`test_predictor_model_error_propagates`）；冪等與 DLQ 有 acceptance `test_shadow_duplicate_create_event_produces_one_prediction`、`test_shadow_undecodable_message_lands_in_dlq_...` 與既有 `test_inference_consumer.py` |
| SQL 安全 | `CACHE_QUERY` 的表名以 `str.replace` 代入，但先檢查只接受 `ROLE_TARGETS` 內的表名，否則 ValueError（單元測試含注入字串、未送查詢）；`model_version` 仍參數化 |
| 威脅與對策（7.27「使用者看到的情緒」「shadow 服務」） | 分開 topic 與表；acceptance 確認 `predictions` 沒有 shadow 版本；截斷與 `INFERENCE_THREADS` 經 `load_classifier(threads=settings.threads)` 傳入（acceptance `test_shadow_role_uses_classifier_with_inference_threads`） |
| conftest | `CLICKHOUSE_TOPICS` 加入 `names.PREDICTIONS_SHADOW` |
| 文件同步 | 7.27 只改 `require_primary` 那一句為現況，未動 D-025 相關句；「載入」段落描述仍正確 |
| TODO 標記 | `TODO(bert-shadow-inference)`、`require_primary` 於 src／tests／docs 無殘留 |
| 覆蓋率 | `main()` 由 acceptance 以 thread 實際執行；新增的 `load_cache` 分支有單元與整合測試 |

## 非阻擋備註（不需在本 PR 處理）

- `test_inference_consumer.py` 改用 `FakeClassifier` 後，整合測試不再端到端跑真的 sklearn pipeline；`SklearnClassifier` 由 bert-classifier 的單元測試涵蓋，primary 的 `main()` 由 acceptance `test_primary_*` 跑過，可接受
- `test_inference_shadow.py` 的 INSERT 用 f-string 拼常數，僅限測試、值為模組常數，無風險
