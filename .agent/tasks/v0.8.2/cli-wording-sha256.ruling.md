TEST_WRONG 5e088ac

驗收測試 lock 檢查：跟 lock（commit 84bae9e）時一樣，沒被改過

## 依據（契約條文）

| 編號 | 來源 | 條文 |
|---|---|---|
| C1 | `docs/development-spec.md` 第 6 章匯入步驟 3 | 「一律印出整包 SHA-256，`--sha256` 必填…不符拒絕；檔案不存在、不是 zip、版本已存在、驗證失敗都印一行中文說明與下一步並以非 0 結束」 |
| C2 | 7.30 F #270 | 「`import_model --sha256` 改必填…，仍先印實際值再比對」 |
| C3 | 7.30 F #263 | 「`import_model` 的錯誤一律一行、`error: ` 開頭、中文、帶下一步」 |
| C4 | 7.30 派工順序第 5 列 | 驗收測試「五種錯誤一行、`error:` 開頭、含中文、無 traceback、結束碼 1」 |

讀法：C3、C4 的「一行」講的是錯誤訊息本身（`error:` 那一行），C1、C2 另外要求在比對前先印一行整包 SHA-256。兩者並存的輸出是「SHA-256 一行＋error 一行」，條文之間沒有矛盾。既有的 `test_cli_failure_message_is_short`（`<= 3` 行）也是照這個讀法寫的。

## 逐條判定

| 測試 | 契約 | 判定與理由 |
|---|---|---|
| `tests/unit/acceptance/cli-wording-sha256/test_cli_wording_sha256_acceptance.py::assert_one_line_error` 的最後一條斷言（「error 行之外不可再有其他非空行」） | C1、C2 | **測試錯**。照 C2 先印實際值再比對的實作，在 zip 檔存在的失敗路徑一定多出一行 SHA-256，這條斷言會失敗。它把「錯誤一行」擴大成「整個輸出只有一行」，跟 C1 的「一律印出」矛盾 |
| 同檔用到 `assert_one_line_error` 的測試：`::test_not_a_zip_prints_one_chinese_line`、`::test_existing_version_says_no_overwrite_and_next_step`、`::test_sha256_mismatch_prints_actual_and_says_redownload`、`::test_validation_failure_prints_one_chinese_line`，以及經 `_fail_line` 用到的 7 個 `::test_*_reason_is_chinese` | C1～C4 | 因為上一列的 helper 而錯；各測試自己的斷言（不會覆寫、`models/`、實際值、重新下載、原因要中文）都符合契約，不用改 |
| `::test_missing_zip_prints_one_chinese_line_with_path_once` | C3 | 符合契約：檔案不存在算不出 SHA-256，輸出只有一行是對的。helper 改完以後照樣通過 |
| `tests/unit/acceptance/import-model-hardening/test_import_model_hardening_acceptance.py::test_cli_failure_message_is_short` | C3 | 符合契約（`<= 3` 行，容得下 SHA-256 行），不用改。worker disputes 把它也列進去，這部分不成立 |
| `::test_missing_sha256_option_exits_2_and_names_option`、`::test_help_describes_sha256_as_notebook_last_cell`、`::test_derive_model_help_describes_both_arguments`、`tests/unit/acceptance/replay-alert-repro/test_replay_warmup_no_false_warning.py` | #263、#270、#271 | 符合契約，不在爭議範圍 |

## 測試要怎麼改（qa「A」）

1. `assert_one_line_error` 加參數 `zip_path: Path | None`：`error:` 行仍然要剛好一行、含中文。另外，除了 `error:` 行，**最多再一行非空行**，而且那一行必須含 `sha(zip_path)`（就是整包 SHA-256 的那行）；不准有其他行。`zip_path` 給 None（檔案不存在）時維持「整個輸出只有一行」。
2. 補上 C1 這次漏測的部分：不是 zip、版本已存在、內容驗證失敗、整包不符這四條路徑，輸出（stdout+stderr）都要含 `sha(zip_path)`。整包不符這條，SHA-256 寫在 error 行裡就算數，不強制多一行。順序（先印再比對）跨 stdout／stderr 沒辦法穩定斷言，不測。
3. `_fail_line` 把 `zip_path` 傳給 helper。

## qa 證據檔（`.agent/reports/cli-wording-sha256.qa.md`，FAIL 1017452）的各項

成立：
- #1 ModelPackageError 原因是英文：在 1017452 成立（違反 #263「各 ModelPackageError 的原因改中文」）。worker 在 5e088ac 改掉了，鎖定的 `::test_*_reason_is_chinese` 7 條通過（我在 5e088ac 實跑三個驗收目錄：64 passed）。
- #2 整包 SHA-256 不是「一律印出」：成立。現在的實作（`src/radar/ml/training/import_model.py` `main()`）只在成功後才 `log.info("package sha256 …")`，不是 zip、版本已存在、驗證失敗都不印，違反 C1、C2。測試照上面改好後，worker 要把 `log.info("package sha256 %s", digest)` 移到算完 digest、比對之前。
- #3 缺 #1、#2 的測試：成立。#1 已由 84bae9e 補上，#2 照上面第 2 點補。

不成立：無。

## 契約問題

- 不用改規格。如果要避免以後又讀錯，可以把 7.30 #263 的開頭「`import_model` 的錯誤一律一行」改成「`import_model` 的錯誤訊息一律一行（另有一行整包 SHA-256，見 #270）」。這只是把字寫清楚，不屬於決策分級四類，manager 可以併進文件單。
- 派工單「驗收測試」寫的 `test_cli_prints_package_sha256_without_option`，在 647ef66 已經改名成 `::test_cli_prints_package_sha256_with_option`，這裡只說明名稱對不上，跟判定無關。
