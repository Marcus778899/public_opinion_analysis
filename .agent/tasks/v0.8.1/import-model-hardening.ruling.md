TEST_WRONG 37e4bd3

# 仲裁：import-model-hardening

依據：派工單 `tasks/import-model-hardening.md` 驗收條件、開發規格 7.27（worktree 版）、`reports/import-model-hardening.json` disputes。
測試目錄來源：`tests/unit/acceptance/import-model-hardening/` 只有 qa 的 `be5af53 test(import-model-hardening)` 動過；worker 的 `37e4bd3` 沒有改驗收測試（只改負責檔案三個）。

## 判定

| 測試 | 契約條文 | 判定與理由 |
|---|---|---|
| `test_import_model_hardening_acceptance.py::test_encrypted_member_raises_package_error` | 派工單驗收條件 4：「加密成員……丟 `ModelPackageError`」（#162 第 2 點） | **測試錯**。實測（Python 3.12.13）：`ZipInfo.flag_bits |= 0x1` 後 `ZipFile.writestr` 會把 `flag_bits` 改回 `0x0`，讀回的成員 `flag_bits` 是 `0x0`、內容可正常讀出。測試造出的是合法未加密包，任何符合契約的實作都會匯入成功 → `DID NOT RAISE`。實作（`import_model.py:54` 檢查 `flag_bits & 0x1`）不是失敗原因。 |
| `tests/unit/ml/test_stage8_interfaces.py::test_cross_task_function_signatures[import_model-expected3]` | 派工單驗收條件 3（新增選填 `--sha256`）；7.27 檔案分工：此檔歸 `bert-skeleton`，「要改簽名先改本節」 | **測試需同步**（非實作錯）。新增 keyword-only、預設 `None` 的 `sha256` 是派工單明訂範圍，且不破壞既有呼叫（`import_model(zip_path, models_dir)` 照常可用，`bert-integration` 等跨單呼叫不受影響）。7.27 本節沒有逐一列出 `import_model` 的 Python 簽名，簽名的唯一記錄就是此測試檔；worker 已改 7.27 流程表第 3 列與威脅表（屬負責範圍），符合「先改本節」的要求。此檔不在本單負責檔案，worker 不可改。 |

## 測試應該怎麼改

1. `test_encrypted_member_raises_package_error`（qa 改）：先用一般方式 `writestr(name, data)` 寫出 zip，寫完再改位元組把加密旗標設上——對每個中央目錄記錄（`b"PK\x01\x02"`，旗標在 +8）與本地檔頭（`b"PK\x03\x04"`，旗標在 +6）的 2 bytes little-endian 值 `|= 0x1`，寫回檔案。已實測：改完後 `zipfile` 讀到的 `flag_bits` 是 `0x1`。其餘斷言（丟 `ModelPackageError`、`models/` 沒有殘留）不變。
2. `test_stage8_interfaces.py`（manager 把此檔加進本單負責檔案，或由 qa／bert-skeleton 擁有者改）：
   - 期望值改為 `["zip_path", "models_dir", "sha256"]`；
   - 另加一條斷言 `sha256` 是 `KEYWORD_ONLY` 且預設 `None`（比照同檔 `test_max_batch_tokens_is_keyword_only_for_loading`），鎖住「不影響既有兩參數呼叫」這個跨單介面性質。

## 契約問題

- 7.27「要改簽名先改本節」但本節沒有 `import_model` 的簽名可改，簽名只存在於 `test_stage8_interfaces.py`。建議在 7.27 檔案分工或模型包流程處補一句 `import_model(zip_path, models_dir, *, sha256=None)`，或把規則改成「改簽名同步改 `test_stage8_interfaces.py` 並列入該單負責檔案」。非四類決策，不需 D-編號。
