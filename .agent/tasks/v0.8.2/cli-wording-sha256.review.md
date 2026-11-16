APPROVE 4b06d92

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 上一輪退回項（7.30 F #263：sha256 不符要說「不要改填實際值」） | `import_model.py:135-138` 改成「整包 zip 的 sha256 不符（實際 <hex>），請重新下載；不要把 --sha256 改填實際值」，仍是一行、`error:` 開頭、rc=1；`test_main_sha256_mismatch_shows_actual_and_redownload` 補了這段文字的斷言 |
| 這輪改動範圍 | `5a60259..4b06d92` 只動 `import_model.py` 與 `tests/unit/ml/training/test_import_model.py`，都在負責檔案內 |
| PR 檔案清單 | src 3 檔、單元測試 3 檔在負責範圍；驗收測試 3 檔是 qa 的 commit（仲裁 lock 檢查：沒被改過） |
| 已 lock 驗收測試 | `test_sha256_mismatch_prints_actual_and_says_redownload` 只驗實際值與「重新下載」，拿掉「可能下載不完整」不影響，實跑通過 |
| 其餘項目（先印再比對、各 ModelPackageError 原因中文、`--sha256` 只在 CLI 必填、derive `--help`、回放警告「舊訊息」） | 與上一輪 review 相同，未再變動，符合 |
| 寫死設定值、安全 | 沒有新設定值；L-2 對策文案補齊 |
| 本機驗證 | worktree 內 `PYTHONPATH=$(pwd)/src`（`radar.__file__` 指向 worktree）：三個驗收目錄＋`tests/unit/ml/training`＋`tests/unit/streaming/test_replay.py` 245 passed；`ruff check` All checks passed；`ruff format --check` 328 files already formatted；`grep -rn "TODO(cli-wording-sha256)" src tests` 無結果；手動 `import_model --zip <非 zip> --sha256 <64 個 0>` 輸出 INFO sha256 一行＋上述 error 一行，rc=1 |
| CI（headRefOid 4b06d92） | Check、Integration Test、Security 都 SUCCESS |

## 非阻擋（沿用上一輪，manager 自行決定）

- `src/radar/streaming/replay.py` 警告結尾「（開發規格 7.20）」，7.30 #271 建議文案為「（開發規格 7.20 步驟 1）」。
- `main()` 先比對 digest 後 `import_model(..., sha256=...)` 又重算一次整包雜湊；為了保持函式介面不變，可接受。
