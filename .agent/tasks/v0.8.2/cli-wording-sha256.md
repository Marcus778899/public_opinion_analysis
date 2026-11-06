# 派工單 cli-wording-sha256

- **類型**：fix
- **負責**：backend
- **目標**：import_model 錯誤訊息改成中文一行帶下一步、`--sha256` 在 CLI 必填、derive_model `--help` 補參數說明、回放殘留警告改中文（#263、#270、#271 文案）
- **背景**：UAT v0.8.1 F-6、F-7、F-9（`docs/uat/v0.8.1.md`）；資安 v0.8.1 L-2（`docs/security/v0.8.1.md`）
- **設計依據**：`docs/development-spec.md` 7.30 F 與派工順序第 5 列、第 6 章匯入步驟；D-042
- **相依**：無
- **負責檔案**：
  - `src/radar/ml/training/import_model.py`
  - `src/radar/ml/training/derive_model.py`
  - `src/radar/streaming/replay.py`
  - `tests/unit/ml/training/test_import_model.py`
  - `tests/unit/ml/training/test_derive_model.py`
  - `tests/unit/streaming/test_replay.py`
- **禁區**：不改文件（與 7.30 不符時回報 manager）；`--sha256` 只在 CLI 必填，函式介面不變
- **驗收測試**：
  - `tests/unit/acceptance/cli-wording-sha256/`
  - `tests/unit/acceptance/import-model-hardening/test_import_model_hardening_acceptance.py`（只限沒帶 `--sha256` 的 CLI 測試：`test_cli_missing_zip_…`、`test_cli_not_a_zip_…`、`test_cli_existing_version_…`、`test_cli_tampered_package_…`、`test_cli_failure_message_is_short`、`test_cli_prints_package_sha256_without_option`）
  - `tests/unit/acceptance/replay-alert-repro/test_replay_warmup_no_false_warning.py`（`WARNING_KEYWORD` 改成中文）
- **驗收條件**：
  - [ ] 五種錯誤（不存在、不是 zip、版本已存在、sha256 不符、驗證失敗）都是一行、`error:` 開頭、含中文與下一步、無 traceback、結束碼 1
  - [ ] 不給 `--sha256` 結束碼 2 且提示該參數
  - [ ] `derive_model --help` 兩個參數都有說明
  - [ ] 回放殘留警告含「舊訊息」
  - [ ] `make check` 通過、改到的程式碼覆蓋率達門檻
- **驗證指令**：`make check`；`uv run pytest tests/unit/acceptance/cli-wording-sha256 tests/unit/acceptance/import-model-hardening tests/unit/acceptance/replay-alert-repro -v`
- **回報檔**：`.agent/reports/cli-wording-sha256.json`

## 執行資訊（ae task 產生）

- Issue：#295
- 分支：`fix/cli-wording-sha256`（從 develop 開出）
- 工作目錄：`.worktrees/cli-wording-sha256`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`

## 追加 2026-11-04

### .agent/reports/cli-wording-sha256.qa.md

FAIL 1017452

## 環境
PYTHONPATH=<worktree>/src；確認 `radar.__file__` 指向 .worktrees/cli-wording-sha256/src。

## 通過的項目（自己執行）
- `uv run pytest` 三個驗收目錄 + tests/unit/ml/training + test_replay：234 passed
- `uv run pytest tests/unit -n auto --cov`：1904 passed；覆蓋率 derive_model 98%、import_model 99%、replay 95%
- `ruff check` All checks passed；`ruff format --check` 328 files already formatted；無 TODO(cli-wording-sha256)
- 手動 CLI（真實執行）：
  - 不存在 -> `error: 找不到 … ，請確認 --zip 路徑` rc=1
  - sha256 不符 -> `error: 整包 zip 的 sha256 不符（實際 <hex>），…請重新下載` rc=1
  - 目錄/無法讀 -> `error: 無法讀取 …（Is a directory）…` rc=1
  - 不給 --sha256 -> usage，`the following arguments are required: --sha256`，rc=2
  - `derive_model --help` 兩個參數都有中文說明

## 問題（FAIL）

### 1. 不是 zip 的錯誤仍含英文原因（違反「含中文」「各 ModelPackageError 的原因改中文」，開發規格 7.30 #263）
重現：
```
echo notzip > $TMPDIR/a.zip
PYTHONPATH=<worktree>/src uv run python -m radar.ml.training.import_model --zip $TMPDIR/a.zip --sha256 $(shasum -a 256 $TMPDIR/a.zip | cut -d' ' -f1)
```
輸出：`error: …/a.zip 不是合格的模型包（not a valid zip file），請確認是 notebook 產生的 zip 並重新下載`
`import_model.py` 第 50、55、58、60、68、71、80、82、86、88、104 行的 `ModelPackageError` 原因全是英文（例 `zip members must be exactly [...]`、`sha256 mismatch for <name>`），都會原樣出現在 CLI 訊息裡。規格 #263 要求「各 ModelPackageError 的原因改中文」。
注意：既有測試只驗「含中文」，外層句子就滿足，所以沒抓到。

### 2. 與開發規格不一致：整包 SHA-256 不再「一律印出」（第 6 章匯入步驟、7.30 #270）
規格第 6 章步驟 3：「一律印出整包 SHA-256」；7.30 #270：「仍先印實際值再比對」。
worker 把 `log.info("package sha256 …")` 移到匯入成功之後（open_questions 自承）。結果：
- sha256 不符：實際值只出現在 error 訊息裡（尚可）。
- 不是 zip／版本已存在／內容驗證失敗／找不到檔案：完全不印整包 SHA-256（上面重現 #1 的輸出只有一行 error，沒有 sha256）。
- 版本已存在時，整包值在 `import_model()` 內部才算，CLI 先算的 digest 也不印。
這與文件「一律印出」不符。禁區規定不改文件，不一致應回報 manager 決定：(a) 改程式回到「先印再比對」（但與「失敗只有一行」的驗收條件衝突，需 manager 確認印在 stderr/stdout 是否算一行），或 (b) 由 architect 改規格為「成功後印出（不符時帶在錯誤訊息）」。我不自行決定以哪邊為準。

### 3. 沒有針對 #1、#2 的測試
下一輪補成測試：不是 zip／驗證失敗的訊息不含英文原因；SHA-256 輸出行為依 manager 決定後固定。

## 其他觀察（非阻擋）
- import_model 本地重複定義 ONNX_MODEL_FILE／TOKENIZER_FILE，已有單元測試對齊 classifier；可接受。
- 未跑 docker 整合測試（本單不碰 DB/Kafka）。
- derive_model 在 sandbox 會印 onnxruntime telemetry 行，規格明說不處理。

manager 補充：
- 第 1 點（ModelPackageError 原因仍是英文）照修，qa「A」先補測試。
- 第 2 點：已鎖定的驗收測試要求失敗路徑只有一行（`assert_one_line_error`），與開發規格第 6 章「一律印出整包 SHA-256」衝突。qa「A」這輪不要針對第 2 點加測試；worker 不要自行選邊，在回報的 `disputes` 列出這個衝突（引用測試與規格條文），由 architect 仲裁。

## 追加 2026-11-04

### .agent/reports/cli-wording-sha256.review.md

REQUEST_CHANGES 5a60259

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 改動檔案 vs 負責檔案 | src 3 檔與單元測試 3 檔都在負責範圍；驗收測試 3 檔是 qa 的 commit（647ef66、84bae9e、3e3a993），仲裁 lock 檢查已確認沒被改 |
| `--sha256` 只在 CLI 必填（禁區） | `main()` 用 `required=True`；`import_model(..., sha256: str \| None = None)` 介面沒變，符合 7.30 #270 |
| 先印再比對（C1、C2，仲裁 TEST_WRONG 5e088ac） | `main()` 算完 digest 立刻 `log.info("package sha256 …")`，之後才比對，符合 |
| 各 `ModelPackageError` 原因中文（#263） | `import_model.py` 第 50～104 行全改中文；except 順序正確（`ModelExistsError` 是 `FileExistsError`，排在 `OSError` 前；`FileNotFoundError` 排在 `OSError` 前） |
| 檔案不存在：路徑只出現一次、不帶系統原文 | 符合 |
| 版本已存在：說不會覆寫＋下一步 | 符合（「要重匯請先移除 models/<版本>/」） |
| derive_model `--help` | 兩個參數都有說明，含「須小於來源值」「-len<N>」，符合 |
| 回放殘留警告含「舊訊息」 | 符合 |
| 寫死設定值、安全 | 沒有新設定值；`--sha256` 必填補上 L-2 |
| 測試是否測到驗收條件 | 驗收測試涵蓋五種錯誤、rc=2、help、警告；單元測試補了 rc=2、mismatch、PermissionError、常數對齊 classifier |
| 本機驗證 | worktree 內 `PYTHONPATH=$(pwd)/src`（`radar.__file__` 指向 worktree）：三個驗收目錄＋`tests/unit/ml/training`＋`test_replay.py` 245 passed；`ruff check` All checks passed；`grep TODO(cli-wording-sha256)` 無結果；手動 `import_model --zip <非 zip> --sha256 00` 輸出 INFO sha256 一行＋error 一行，rc=1 |
| CI | Check、Integration Test、Security 都 pass |

## 要修的問題

1. `src/radar/ml/training/import_model.py:135` — 整包 SHA-256 不符的訊息沒有寫「不要改填實際值」。開發規格 7.30 F #263 寫的是「整包 SHA-256 不符（印實際值，並說要重新下載、不要改填實際值）」。這句是 L-2 的對策：訊息裡印了實際值，使用者照抄重跑就繞過整包比對（7.30 威脅表「模型包被換掉」）。現在只寫「可能下載不完整，請重新下載」— 在同一行加上「不要把 --sha256 改成上面的實際值」這類說明（仍然一行、`error:` 開頭）；`tests/unit/ml/training/test_import_model.py::test_main_sha256_mismatch_shows_actual_and_redownload` 補一條斷言驗證這段文字。驗收測試沒測到這點，所以 qa 兩輪都沒抓到；改了不會讓已 lock 的驗收測試失敗（`test_sha256_mismatch_prints_actual_and_says_redownload` 只驗實際值與「重新下載」）。

## 非阻擋（不用這輪改）

- `src/radar/streaming/replay.py:360` 警告結尾寫「（開發規格 7.20）」，7.30 #271 的建議文案是「（開發規格 7.20 步驟 1）」；意思一樣，manager 可自行決定要不要順手補上。
- `main()` 已先比對 digest，`import_model(..., sha256=args.sha256)` 又會重算一次整包雜湊（大檔多讀一次）；這是為了保持函式介面不變，可接受。
