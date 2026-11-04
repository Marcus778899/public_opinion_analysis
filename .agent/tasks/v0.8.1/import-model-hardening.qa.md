PASS f0bd736

# QA import-model-hardening（PR #233，HEAD f0bd736）

全部在 `.worktrees/import-model-hardening`，`PYTHONPATH=$PWD/src:$PWD`，自己實際執行，未引用回報的 tail。

## 自動檢查

| 指令 | 結果 |
|---|---|
| `uv run pytest tests/unit/acceptance/import-model-hardening tests/unit/ml/training/test_import_model.py tests/unit/ml/test_stage8_interfaces.py -q` | `57 passed in 11.90s` |
| `uv run pytest tests/unit -q`（make check 的第二步） | `1652 passed in 81.59s` |
| `pre-commit run --all-files`（make check 的第一步） | trailing whitespace／end of files／check yaml／ruff／ruff format／bandit 全 Passed |
| `uv run ruff check .`、`ruff format --check .` | `All checks passed!`、`313 files already formatted` |
| `grep -rn "TODO(import-model-hardening)" src tests` | 無結果 |

## 驗收條件

| 條件 | 驗證 | 結果 |
|---|---|---|
| 1 檔案不存在／不是 zip／版本已存在：一行說明、非 0、無 traceback | 實跑 CLI：不存在 `error: nonexist.zip: [Errno 2]...` exit=1 tb=0；截半 zip `error: bad_trunc.zip: not a valid zip file` exit=1 tb=0；目錄 `[Errno 21] Is a directory` exit=1 tb=0；已存在 `error: model version already exists: models/qa-ver` exit=1 tb=0 | OK |
| 2 `--help` 每個參數有說明 | `--zip`、`--sha256` 都有說明文字 | OK |
| 3 `--sha256`：不符拒絕、一律印整包 SHA-256 | 無旗標也印 `package sha256 ...`；`--sha256 0000` exit=1，`error: ...package sha256 mismatch, actual ...`，`models/` 未建立；正確值轉大寫 exit=0 匯入成功 | OK |
| 4 kind 非 onnx 拒絕；加密／不支援壓縮丟 ModelPackageError | 驗收測試與單元測試通過（見上 57 passed）；未手動造加密包 | OK |
| 5 開發規格 7.27 同步、make check、TODO grep | diff 看過第 3 列與威脅表；其餘見上 | OK |

## 本輪 review 3 項

1. 損壞成員：把 ok.zip 第一個成員資料中間改 1 byte（`bad2.zip`／`bad_data.zip`）跑 CLI，輸出 `error: bad2.zip: corrupted zip member: model.onnx`，exit=1，Traceback 數 0，`models/` 無殘留。程式 `import_model.py:60-64` 捕捉 `BadZipFile、zlib.error、EOFError`。OK
2. 威脅表重複句：`docs/development-spec.md` 推論主機列只剩「並可用 `--sha256` 比對整包 zip（甲方對照 notebook 最後一格印出的整包值）」，舊句已刪。OK
3. 模組 docstring 用法行：`--zip <model_version>.zip [--sha256 <hex>]`。OK

## 邊界與寫死設定

- 無寫死 port／網址／token；`MODELS_DIR = Path("models")` 為既有設定。
- sha 不符時整包多雜湊兩次：review 已判不用改，不列問題。
- 2 GB 讀入記憶體屬禁區，不列問題。

## 問題數量

0
