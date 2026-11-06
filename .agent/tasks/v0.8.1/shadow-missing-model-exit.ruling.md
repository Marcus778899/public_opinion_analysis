TEST_WRONG d51ba3c

# 仲裁 shadow-missing-model-exit（PR #217）：CI 整合驗收 8 個失敗

## 失敗原因（已確認）

CI run 40810929085 的 log，8 個失敗的測試各有一行（路徑是各測試的 `tmp_path`）：

```
ERROR-(inference|radar.ml.inference.main.exit_missing_model:195)=> shadow 找不到模型 /tmp/pytest-of-runner/.../test_shadow_role_writes_only_s0/model_card.json；請在 .env 設定 INFERENCE_SHADOW_MODEL_VERSION …
```

- `tests/integration/acceptance/bert-shadow-inference/test_shadow_service.py` 的 `env` fixture 設 `INFERENCE_MODEL_DIR=str(tmp_path)`。這是空的資料夾，`load_classifier` 被 monkeypatch 換掉，所以以前從來沒讀過資料夾的內容
- 本單在 `main()` 加了 shadow 啟動檢查（`check_shadow_model`：資料夾裡沒有 `model_card.json` 就以 78 結束），所以 `run_service` 的執行緒在 `load_classifier` 之前就因 `SystemExit` 結束，`done` 沒有被設定，assert 失敗
- primary 的測試（`test_primary_role_still_writes_only_primary_topic`）和 `test_shadow_clickhouse.py` 都通過，與「primary 不檢查」的說法一致
- 沒有另外跑 docker：CI log 已經直接顯示原因，不必在本機重現

## 測試目錄的 git 紀錄

| 目錄 | commit | 判定 |
|---|---|---|
| `tests/unit/acceptance/shadow-missing-model-exit/` | 只有 `9ce8197 test(shadow-missing-model-exit)`（qa） | 沒有被 worker 改過 |
| `tests/integration/acceptance/bert-shadow-inference/` | `0f4b100 test(bert-shadow-inference)`、`61ae81b test(bert-onnx-length-batching)` | 兩個都是 qa 的 test commit，本單沒有碰 |

## 逐條判定

| 測試 | 契約條文 | 判定與理由 |
|---|---|---|
| 本單 `test_shadow_version_blank_in_compose_style_dir_exits_nonzero_and_names_env_var`、`test_shadow_model_dir_not_exist_*`、`test_shadow_with_model_dir_present_still_runs`（資料夾裡有 `model_card.json` 才往下跑） | 開發規格 7.27 第 1287 行：「shadow 啟動時先檢查：`INFERENCE_MODEL_DIR` 未設或沒有 `model_card.json` … 以結束碼 78 離開」；#172／派工單驗收條件 1 | **正確**。compose 在 `INFERENCE_SHADOW_MODEL_VERSION` 沒設時會組成 `/app/models/`，這個資料夾存在，所以只檢查「資料夾存在」抓不到 F-2 的情況，一定要檢查 `model_card.json`。測試不用改 |
| 本單實作 `check_shadow_model`／`main()` | 同上 | **符合契約**。實作不用改 |
| `bert-shadow-inference/test_shadow_service.py` 中用 `env` fixture、以 `InferenceRole.SHADOW` 跑 `run_service` 的 8 個測試 | 7.27 模型包格式（第 81、1261 行：`models/<model_version>/` 一定有 `model_card.json`）；第 870 行「`INFERENCE_MODEL_DIR` 指向 `models/<model_version>/`」；第 1287 行的啟動檢查 | **TEST_WRONG**。fixture 給 shadow 的是一個空資料夾，不是合規格的模型資料夾。照現行契約，shadow 碰到這種資料夾就應該以 78 結束，所以測試的前提和契約互相矛盾。測試要驗的行為（topic、group、快取、冪等、DLQ、threads）跟模型資料夾的內容無關，補上卡片就好，不必改 assert |

## 要怎麼改（給 qa；manager 把這個檔加進本單的負責範圍後重新鎖定）

檔案：`tests/integration/acceptance/bert-shadow-inference/test_shadow_service.py`，只改 `env` fixture：

- 在 `card = make_card(e.model_version)`（約第 102 行）後面加一行，把卡片寫進 `INFERENCE_MODEL_DIR` 指向的資料夾，讓它跟真實的模型包一樣：
  `(tmp_path / "model_card.json").write_text(card.model_dump_json(), encoding="utf-8")`
- `load_classifier` 照舊用 fake（這個檔不讀卡片內容，只需要檔案存在；用 `ModelCard` 序列化，內容也符合格式）
- 不改任何測試函式和 assert。`test_shadow_role_uses_classifier_with_inference_threads` 自己另建的 `card` 只用在 fake 的回傳值，不用處理
- 驗證：`docker compose --env-file .env -f .worktrees/shadow-missing-model-exit/compose.yaml run --rm test`（或只跑 `tests/integration/acceptance/bert-shadow-inference/`），8 個 shadow 測試都通過，跑完 `down -v`

## 契約問題

- 無。第 1287 行是本單在負責範圍（7.27 shadow 啟動描述）內新加的，和模型包格式（第 81、1261 行）一致，review 已經看過。不屬於決策分級的四類
