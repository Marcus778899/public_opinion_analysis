APPROVE 49c5db6

# Review ml-cli-usability（PR #216）

## 檢查範圍

- `gh pr diff 216`（8 檔），對照派工單 `tasks/ml-cli-usability.md`、開發規格 7.27、worker 回報、qa 證據
- 負責檔案：變更都在負責檔案內（`src/radar/common/cli.py`、`csv_safe.py` 屬「新增的共用模組」）；沒改 import_model、settings、輸出欄位；`MODEL_VERSION_RE` 從 import_model import
- 驗收測試目錄只有 qa 的 `e5a7c80 test(ml-cli-usability)` commit 改過
- 本機（`PYTHONPATH=<worktree>/src`，已確認 `radar.__file__` 指向本 worktree）：`pytest tests/unit/acceptance/ml-cli-usability tests/unit/ml -q` 387 passed；`ruff check src tests` 通過；`grep -rn "TODO(ml-cli-usability)" src tests` 無結果
- CI（run 40809504702）：Check、Integration Test、Security 全過；Integration Test 的 `make coverage` 為 1866 passed（含 tests/integration）

## 驗收條件對照

| 條件 | 判定 | 依據 |
|---|---|---|
| #173 evaluate 模型資料夾不存在／不是模型包 | 符合 | `check_model_dir` 擋不存在；`load_classifier` 的 FileNotFoundError 轉 `fail`；`fail` 丟 SystemExit，不被 `@log.catch`（只抓 Exception）吞掉 |
| #175 缺 ClickHouse 變數 | 符合 | `load_settings` 由 pydantic `missing` 錯誤組出 `CLICKHOUSE_*` 名稱與 `uv run --env-file .env` 提示；非 missing 的驗證錯誤照常往上丟 |
| #174 `--help` | 符合 | evaluate `--model`、compare `--a/--b/--since` 都有說明；`--since` 有 ISO 範例與「沒寫時區視為 UTC」 |
| #176 CSV | 符合 | compare disagreements 與 cross_check 共用 `radar.common.csv_safe.csv_safe`；只處理字串欄（board、title），數值與 polarity 不變 |
| #168 版本格式 | 符合 | `model_version_arg` 用 `MODEL_VERSION_RE.fullmatch`；現行版本命名（例 `tfidf-lr-202610151237`）符合 |
| #168 同列取值 | 符合 | `argMax((polarity, arrayMax(mapValues(scores))), predicted_at)` 取 tuple 再拆 `pick.1/pick.2`，polarity 與 score 必來自同一列 |

## manager 指定的兩點

1. **#168 SQL 只有文字層級的驗收測試**：CI 整合測試有實際跑到新 SQL。`fetch_pairs` 每次都會組 `_latest_prediction`，`tests/integration/acceptance/bert-compare/test_compare_queries.py`（`test_fetch_pairs_returns_board_title_and_latest_prediction_of_each_version` 驗 polarity 與 score 取最新一筆、`test_main_writes_comparison_report_and_disagreement_csv` 等）與 `tests/integration/ml/test_compare.py` 都在 CI 的 Integration Test 通過，代表 ClickHouse 接受這段語法，「取最新一筆」的語意也沒變。同一 `predicted_at` 並列的情況沒有 DB 層測試；並列時本來就是任選一列，tuple 保證同列，這部分靠文字檢查就夠了。不阻擋。
2. **evaluate 的 ClickHouse 檢查在 `load_classifier` 之後**：驗收條件沒規定順序，`test_evaluate_missing_clickhouse_env_names_variables_and_hint` 用 tiny 模型包驗過訊息與結束碼。為了相容已合併的 bert-onnx-length-batching 驗收測試，放在後面是合理的，NOTE 也寫了理由。代價是使用者要等模型載完才看到缺變數的訊息（evaluate 載入只要幾秒）。不阻擋。

## 非阻擋備註

- `fail` 用 `print(..., file=sys.stderr)`：這是指令列給使用者看的一行錯誤，不算 log，不違反 log 規範
- evaluate 只把 FileNotFoundError 轉成一行訊息；`model_card.json` 格式壞掉時仍會有 traceback，不在本單 #173 範圍
- cross_check 的 `post_id` 沒經過 `csv_safe`：post_id 是 `<board>.<檔名>`，開頭不會是公式字元，風險可忽略（qa 也提到）
- 單元測試裡有 `import pytest` 等寫在函式內的區域 import，屬風格問題，lint 已通過
