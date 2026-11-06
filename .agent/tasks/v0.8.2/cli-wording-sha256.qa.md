PASS 4b06d92

## 環境
worktree 內 `PYTHONPATH=$(pwd)/src`；`radar.__file__` = .worktrees/cli-wording-sha256/src/radar/__init__.py

## 自己執行的驗證
- `make check`（pre-commit run --all-files + uv run pytest tests/unit）：pre-commit 通過（make 才會往下跑 pytest），`1915 passed in 133.70s`
- `uv run pytest` 三個驗收目錄 + tests/unit/ml/training + test_replay.py：`245 passed`
- `ruff check .`：All checks passed；`ruff format --check .`：328 files already formatted
- 覆蓋率（改到的檔）：derive_model 98%、import_model 97%、replay 91%
- `grep -rn "TODO(cli-wording-sha256)" src tests`：無結果

## 手動 CLI（真實執行，rc 為結束碼）
- 非 zip（sha 正確）：INFO 一行整包 sha256 + `error: …a.zip 不是合格的模型包（不是有效的 zip 檔），請確認是 notebook 產生的 zip 並重新下載`，rc=1（原因已中文）
- sha256 不符：`error: 整包 zip 的 sha256 不符（實際 <hex>），請重新下載；不要把 --sha256 改填實際值`，rc=1（上輪 review 問題已修；單元測試 test_import_model.py:164 有斷言）
- 檔案不存在：`error: 找不到 …/none.zip，請確認 --zip 路徑`，rc=1，無 traceback
- 不給 --sha256：`the following arguments are required: --sha256`，rc=2
- `derive_model --help`：--model、--max-len 都有中文說明

## 驗收條件對照
1. 五種錯誤一行、error: 開頭、中文、下一步、rc=1：通過（不存在、非 zip、sha 不符手動確認；版本已存在、驗證失敗由驗收測試覆蓋並通過）
2. 不給 --sha256 rc=2 並提示：通過
3. derive_model --help：通過
4. 回放警告含「舊訊息」：驗收測試通過
5. make check 與覆蓋率：通過

## 其他
- 無寫死設定值；--sha256 只在 CLI 必填，函式介面不變
- 未跑 docker 整合測試（本單不碰 DB/Kafka）
- 非阻擋：replay 警告結尾未帶「步驟 1」；main 重算雜湊一次（review 已列為可接受）
- 無 scan 通道項目
