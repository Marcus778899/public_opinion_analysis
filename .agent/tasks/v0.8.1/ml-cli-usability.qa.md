PASS 49c5db6

# QA ml-cli-usability（PR #216）

驗證時固定 `PYTHONPATH=<worktree>/src`，`radar.__file__` = `.worktrees/ml-cli-usability/src/radar/__init__.py`（確認載入本 worktree）。

## 指令與結果
- `pytest tests/unit/acceptance/ml-cli-usability tests/unit/ml -q`：387 passed
- `pytest tests/unit -q`：1483 passed
- `ruff check .`：All checks passed；`ruff format --check .`：299 files already formatted
- `grep -rn "TODO(ml-cli-usability)" src tests`：無結果

## 手動執行（env -i 清空環境）
- evaluate --model /nonexistent：`error: 找不到模型資料夾 /nonexistent`，exit 1，無 traceback（#173）
- evaluate --model <空資料夾>：`error: ... 不是模型資料夾（找不到 .../model_card.json）；請先用 import_model 匯入`，exit 1
- compare、cross_check 缺環境變數：`error: 缺少環境變數 CLICKHOUSE_USER, CLICKHOUSE_PASSWORD；請用 `uv run --env-file .env python -m ...` 執行以載入 .env`，exit 1，無 traceback（#175）
- evaluate 的缺變數路徑：用有效模型包才走得到，由單元／驗收測試涵蓋（未手動跑）
- `--help`：evaluate 的 --model、compare 的 --a/--b/--since 都有說明；--since 有 ISO 範例與「沒寫時區視為 UTC」（#174）
- compare `--a 'bad ver!'`、`--b ../x`：argparse 拒絕，使用 MODEL_VERSION_RE（#168）
- csv_safe：`= + - @ \t \r` 開頭加 `'`；`abc`、空字串、`a=b`、` =x` 不變；compare disagreements 與 cross_check 同用 `radar.common.csv_safe.csv_safe`（#176）

## 判斷：evaluate 的 ClickHouse 檢查在 load_classifier 之後
仍滿足驗收條件（條件只要求缺變數時的訊息、非 0、無 traceback，未規定順序）；缺點是模型載入完才報錯，使用者要多等一次載入。可接受，已有 NOTE 說明。

## 未能實跑（環境）與備註
- #168 的 ClickHouse SQL（`argMax((polarity, arrayMax(...)), predicted_at)` 取 tuple）未能對真實 ClickHouse 驗證：`docker compose ... run --rm test` 建置失敗，原因是 .env 的 GRAFANA_VERSION 值為 `13.0.2ㄥ`（含多餘字元，invalid reference format），與本單無關。語法為標準 ClickHouse，單元測試只做文字層級檢查；既有整合測試 tests/integration/ml/test_compare.py、tests/integration/acceptance/bert-compare 會在 CI 跑到此 SQL，請以 CI 結果為準。建議甲方修 .env。
- 小建議（不阻擋）：cross_check 的 post_id 欄未經 csv_safe，但 post_id 由看板名開頭，風險低。
