PASS 8f1ce7a

# bert-compare 驗證（HEAD 8f1ce7a，PR #167）

CI（含 gitleaks 已知誤判 D-026）不列入判定。

## 驗收測試未被改動
`git diff 3ceed26 HEAD --stat -- tests/integration/acceptance/bert-compare` 輸出為空（lock 3ceed26 之後無任何變動）。
自 lock 起的變動檔：BOARD.md、docs/decisions.md、docs/development-spec.md、compare.py、tests/integration/ml/test_compare.py、tests/unit/ml/training/test_compare.py（皆在負責檔案或 sync 帶入）。

## 整合測試（目前 HEAD，自己實跑）
- `docker compose ls`：沒有其他堆疊（只有表頭）
- `docker compose --env-file .env -f .worktrees/bert-compare/compose.yaml run --rm test`
  輸出結尾：`8 workers [347 items]` ... `============================= 347 passed in 43.38s =============================`
  （含 acceptance/bert-compare 全部，包括 `test_main_writes_comparison_report_and_disagreement_csv`）
- 已用同一條指令換成 `down -v`，容器、網路、volume 皆移除

## make check 內容
- `pre-commit run --all-files`：trailing whitespace、end of files、check yaml、ruff、ruff format、bandit 全部 Passed
- `uv run pytest tests/unit -q`：`1306 passed in 4.70s`
- `grep -rn "TODO(bert-compare)" src tests`：無結果（exit 1）

## 逐條對照 7.27「比較」
- 一致率、kappa、混淆矩陣（整體、各看板）：`agreement()` 以整數混淆矩陣計算；驗收測試預期值（一致率 4/7、kappa 12/33 = 0.364、各看板）通過。範圍限 `posts_latest FINAL`、`NOT is_deleted`、`created_at >= since`，兩版各取 argMax 最新一筆後 INNER JOIN。已刪除、太舊、只有單版預測的文章被排除，測試通過。
- 對 LLM macro-F1 與篇數：LEFT JOIN `labels`（labeler、目前 `PROMPT_VERSION`、`target IS NULL`、argMax labeled_at）；a=1.000、b=0.667、各 6 篇，main 報告含 `render_llm_section`。
- 不一致 CSV：只含 polarity 不同的列；欄位 `post_id, board, title, polarity_a, score_a, polarity_b, score_b, llm`；標題含逗號與引號可讀回；無標註時 llm 為空而非 "None"。
- 推論延遲：第一次 predicted_at − posts_history `op='c'` 的 changed_at，`changed_at >= since`；p50／p95 線性內插、最大值；primary 與 shadow 各讀自己的表（表名取自 `ROLE_TARGETS`）。
- 信心分布：0.4／0.5／0.6／0.7 低於門檻比例，與門檻以上對 LLM 準確率及篇數；測試通過。
- 查詢全部參數化：值一律走 `{name:Type}` 參數；f-string／`.replace` 只嵌入來自 `ROLE_TARGETS` 常數的表名；有引號版本名的整合測試（`a' OR '1'='1`）當成值處理、回空。
- main 端到端：驗收測試以 monkeypatch 環境變數呼叫 `compare.main()`，產出 `models/<b>/comparison.md` 與 `data/review/disagreements-<a>-vs-<b>.csv`，內容符合預期。
- 寫死設定值：compare.py 內搜尋 localhost、127.0.0.1、token、password、4 位數 port 皆無；只有 `CONFIDENCE_THRESHOLDS`（規格指定值）與相對路徑常數。

## 7.27 回寫與實作一致性
新增的四點與程式逐項相符：`render_llm_section(a,b,pairs)` 由 main 附在 `render_markdown` 後（簽名未變）；kappa 整數運算、全同類回 1.0（`n*n == chance`）；延遲線性內插與 CSV 欄位順序；標註者由 `LABEL_PRIMARY` 經 `build_labeler` 推出、一致率百分比、kappa 與 macro-F1 三位小數。改動範圍只在「比較」節新增段落，未動同節其他處。

## 邊界情況觀察（不構成 FAIL）
- 空表、無重疊、模型版本不在表內：回空／0，有整合與單元測試。
- 未實際對正在運作的 ClickHouse 手動啟動 CLI；main 路徑由整合測試對真實 ClickHouse 覆蓋。

## 問題
無（0 項）。
