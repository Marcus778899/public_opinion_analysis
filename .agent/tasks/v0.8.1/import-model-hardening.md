# 派工單 import-model-hardening

- **類型**：fix
- **負責**：backend
- **目標**：`import_model` 的錯誤提示、`--help` 說明、整包 SHA-256 驗證與 review 建議（#173 import_model 部分、#174 import_model 部分、#177、#162）
- **背景**：UAT v0.8.0 F-3、F-4（docs/uat/v0.8.0.md）、資安 v0.8.0 L-3（docs/security/v0.8.0.md）、bert-model-import review 非阻擋建議（reports/bert-model-import.review.md）；evaluate／compare 部分已由 PR #216 處理
- **設計依據**：上列 issue；`docs/development-spec.md` 7.27「模型包格式」與「威脅與對策」推論主機列（加 `--sha256` 後同步改這一列）；錯誤處理比照 PR #216（印一行說明、非 0 結束、沒有 traceback）
- **相依**：無
- **負責檔案**：
  - `src/radar/ml/training/import_model.py`
  - `tests/unit/ml/training/test_import_model.py`
  - `docs/development-spec.md`（只限 7.27 與 import_model 相關的列）
- **禁區**：不改模型包格式、`MODEL_VERSION_RE`、evaluate／compare；2 GB 讀入記憶體（#162 第 3 點）維持不改
- **驗收測試**：
  - `tests/unit/acceptance/import-model-hardening/`
- **驗收條件**：
  - [ ] 檔案不存在、不是 zip、版本已存在時印一行說明、非 0 結束、沒有 traceback（#173）
  - [ ] `--help` 每個參數都有說明（#174）
  - [ ] 新增選填 `--sha256 <hex>`：給了就比對整包 zip 的 SHA-256，不符時拒絕匯入；不論有沒有給都印出整包 SHA-256（#177）
  - [ ] card 的 `kind` 不是 onnx 時匯入就拒絕；加密成員或不支援的壓縮法丟 `ModelPackageError`（#162 第 1、2 點）
  - [ ] 開發規格 7.27 同步；驗收測試、`make check` 通過；`grep -rn "TODO(import-model-hardening)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/import-model-hardening tests/unit/ml/training/test_import_model.py`；`make check`
- **回報檔**：`reports/import-model-hardening.json`

## 執行資訊（task.py 產生）

- Issue：#232
- 分支：`fix/import-model-hardening`（從 develop 開出）
- 工作目錄：`.worktrees/import-model-hardening`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

### reports/import-model-hardening.ruling.md

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

## 追加 2026-10-29

manager：上一則追加漏了範圍更新，補上。依仲裁 TEST_WRONG，跨單簽名測試併入本單的驗收測試（只有 qa 能改，已在 a279de7 改好）。完整清單如下：

- **驗收測試**：
  - `tests/unit/acceptance/import-model-hardening/`
  - `tests/unit/ml/test_stage8_interfaces.py`

## 追加 2026-10-29

### reports/import-model-hardening.review.md

REQUEST_CHANGES a279de7

# Review import-model-hardening（PR #233，head a279de7）

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 變更檔案 vs 負責檔案 | worker 的 37e4bd3 只動 `import_model.py`、`test_import_model.py`、`development-spec.md`（只動 7.27 流程表第 3 列與威脅表推論主機列）；驗收測試兩檔只有 qa 的 `test(...)` commit 動過（含仲裁追加的 `test_stage8_interfaces.py`） |
| 禁區 | 模型包格式、`MODEL_VERSION_RE`、evaluate／compare、2 GB 讀入記憶體都沒動 |
| 驗收條件 1（#173） | 不存在、不是 zip、目錄、版本已存在：一行 `error: ...`、非 0、沒有 traceback。符合 |
| 驗收條件 2（#174） | `--zip`、`--sha256` 都有 help。符合 |
| 驗收條件 3（#177） | 一律印整包 SHA-256；`--sha256` 大小寫不分、不符時拒絕且沒有留下檔案；`sha256` 是 keyword-only，預設 None（跨單簽名測試已同步）。符合 |
| 驗收條件 4（#162 1、2） | `kind` 不是 onnx 就拒絕；加密旗標、STORED／DEFLATED 以外的壓縮法在讀成員之前丟 `ModelPackageError`。符合 |
| 寫死設定 | 沒有 |
| 測試 | 驗收測試用子行程測結束碼、輸出與「沒有 traceback」，加密測試照仲裁改成直接改位元組，確實測到驗收條件；單元測試涵蓋 `package_sha256`、大寫、不符、kind、加密、bzip2、`main` 的兩條錯誤路徑 |

## 要改的問題

1. `src/radar/ml/training/import_model.py:60-62`：zip 內容損壞（中央目錄正常，壓縮資料或 CRC 壞掉，例如傳輸途中翻了一個位元）時，`zf.open(...).read()` 丟出 `zlib.error` 或 `zipfile.BadZipFile("Bad CRC-32 ...")`，這兩種都不是 `ModelPackageError`／`OSError`，CLI 會印完整 traceback。實測：把 `ok.zip` 第一個成員的資料改一個 byte 後 `python -m radar.ml.training.import_model --zip corrupt.zip`，輸出結尾是 `zlib.error: Error -3 while decompressing data: invalid code lengths set`，有 traceback。這跟同一個 PR 寫進開發規格 7.27 第 3 列的「驗證失敗都印一行說明並以非 0 結束（無 traceback）」矛盾，而且「下載或傳遞途中損壞」正是這個工具最常遇到的情況（沒給 `--sha256` 時就會發生）。**改法**：在讀成員的迴圈外包 `except (zipfile.BadZipFile, zlib.error) as exc: raise ModelPackageError(f"corrupted zip member: {name}") from exc`（或包住整個 `with zf:` 區塊），再加一條單元測試：改壞成員資料的一個 byte，斷言會丟 `ModelPackageError`、CLI 沒有 traceback。
2. `docs/development-spec.md:1325`（威脅表推論主機列）：新加的「並可用 `--sha256` 比對整包 zip（甲方對照 notebook 印出的整包值）」跟舊句「甲方對照 notebook 最後一格印出的值」講的是同一件事，而且舊句被移到 kind／加密那一句後面，看起來像是在講 kind 檢查（違反「同一件事只寫一次」）。**改法**：刪掉舊句「；甲方對照 notebook 最後一格印出的值」，只留新的那句（可以寫成「對照 notebook 最後一格印出的整包值」）。
3. `src/radar/ml/training/import_model.py:3`（模組 docstring 的用法行）：只寫了 `--zip`，沒有 `--sha256`，和開發規格 7.27 第 3 列不一致。**改法**：改成 `python -m radar.ml.training.import_model --zip <model_version>.zip [--sha256 <hex>]`。

## qa 非阻擋觀察的判定

| 觀察 | 判定 |
|---|---|
| 威脅表一列說明重複 | 要改，見第 2 點：除了重複，舊句的位置也會讓人讀錯意思；在負責範圍內，改一行就好 |
| 模組 docstring 沒提 `--sha256` | 要改，見第 3 點：文件和程式要同步，改一行就好 |
| sha 不符時整包最多雜湊三次（`main` 一次，`import_model:91-92` 兩次） | 不用改：只影響效能，而且只在不符、要拒絕匯入的路徑上；最多 2 GB 的包多算幾秒可以接受。順手修的話，`import_model:91-92` 先把結果存成 `actual` 再比對、組訊息就好；不要求 |
