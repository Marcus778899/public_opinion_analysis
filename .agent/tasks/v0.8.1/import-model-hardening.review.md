APPROVE f0bd736

# Review import-model-hardening（PR #233，head f0bd736，第 2 輪）

## 上一輪 3 項

| 項目 | 結果 |
|---|---|
| 1. 損壞 zip 成員 | `_read_members` 讀成員時把 `zipfile.BadZipFile`、`zlib.error`、`EOFError` 轉成 `ModelPackageError("corrupted zip member: ...")`。實測：改壞一個 DEFLATED 成員的資料後跑 CLI，只印一行 `error: ...: corrupted zip member: model.onnx`，沒有 traceback。新的單元測試涵蓋 DEFLATED（`import_model` 丟錯、`models/` 沒有殘留）和 STORED（`main` 的 CRC 錯誤）兩種。已修 |
| 2. 7.27 威脅表重複句 | 刪掉舊句，留「對照 notebook 最後一格印出的整包值」。已修 |
| 3. docstring 補 `--sha256` | 用法行已補。已修 |

## 完整 diff（對 develop）

| 項目 | 結果 |
|---|---|
| 變更檔案 vs 負責檔案 | worker 的 commit（37e4bd3、f0bd736）只改了 `import_model.py`、`test_import_model.py`、`development-spec.md`（只改 7.27 流程表第 3 列與威脅表推論主機列）；兩個驗收測試檔只有 qa 的 `test(...)` commit 改過 |
| 禁區 | 模型包格式、`MODEL_VERSION_RE`、evaluate／compare、2 GB 讀入記憶體都沒有動 |
| 驗收條件 1～4 | 符合（逐條內容見上一輪結果，這一輪沒有變動） |
| 驗收條件 5 | 7.27 已同步；指定測試 57 passed；`make check` 1652 passed；`grep -rn "TODO(import-model-hardening)" src tests` 沒有結果 |
| 寫死設定、安全 | 沒有寫死的設定值；新的例外處理只把錯誤轉成 `ModelPackageError`，不吞錯，也不會留下半成品 |
| qa | `reports/import-model-hardening.qa.md` 判定 PASS f0bd736 |

## 非阻擋（不要求修改）

- sha 不符時整包會雜湊多次（`import_model` 裡的 `package_sha256` 呼叫兩次）：上一輪已判定不用改
