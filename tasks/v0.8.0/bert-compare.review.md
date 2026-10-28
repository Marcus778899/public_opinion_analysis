APPROVE 8f1ce7a

# bert-compare review（PR #167，head 8f1ce7a）

CI 的 gitleaks 失敗為已知誤判（D-026），不列入判定。

## 檢查範圍

| 項目 | 結果 |
|---|---|
| 改動檔案 | 735d1d9 只動 `compare.py`、`tests/unit/ml/training/test_compare.py`、`tests/integration/ml/test_compare.py`；8f1ce7a 只動 `docs/development-spec.md`（追加後的負責檔案）。驗收測試目錄只有 qa 的 3ceed26 |
| 骨架簽名 | `fetch_pairs`、`fetch_latency`、`agreement`、`confidence_buckets`、`render_markdown`、`write_disagreements`、`main` 簽名未變；新增 `render_llm_section`、`macro_f1_vs_llm`、`percentile` 與私有 helper |
| `TODO(bert-compare)` | `grep -rn` 無結果 |
| 表名來源 | `_pairs_query`、`fetch_latency` 的表名只取自 `ROLE_TARGETS[...].table`（7.27「自行決定」角色對照表） |
| 查詢參數化 | 版本、since、labeler、label_version 全走 `{name:Type}`；f-string／`.replace` 只嵌入常數表名與固定參數名；單元與整合測試都以含引號的版本名驗證 |
| 寫死設定 | 無 host、port、token；ClickHouse 走 `ClickHouseSettings()`，標註者走 `LabelingSettings()` |

## 對照 7.27「比較」

| 指標 | 判定 |
|---|---|
| 一致率、kappa、混淆矩陣（整體、各看板） | 各表 `argMax(..., predicted_at)` 取每篇最新、限該版本，INNER JOIN `posts_latest FINAL`（`NOT is_deleted`、`created_at >= since`）；kappa 公式 (n·agreed − Σ行×列)/(n² − Σ行×列) 正確，n² = chance 只發生在兩版集中於同一類，回 1.0 合理 |
| 對 LLM macro-F1 與篇數 | LEFT JOIN `labels`（labeler、`PROMPT_VERSION`、`target IS NULL`、argMax labeled_at）；`labels.polarity` 是 `LowCardinality(String)`，join_use_nulls=0 時缺值為 `''`，`fetch_pairs` 以 `if r["llm"]` 轉 None，正確。`f1_score(labels=list(Polarity), zero_division=0)` 與 `evaluate.py` 同算法 |
| 不一致 CSV | 只列 polarity 不同者、依 post_id 排序、`csv.writer` 處理逗號與引號、無標註寫空字串 |
| 推論延遲 | `min(predicted_at)` − `posts_history` `op='c'` 的 `min(changed_at)`，`changed_at >= since`；p50／p95 線性內插、max |
| 信心分布 | 低於門檻比例以全部篇數為分母；門檻以上（含等於）且有標註者算準確率與篇數 |
| main | 輸出 `models/<b>/comparison.md`、`data/review/disagreements-<a>-vs-<b>.csv`；ClickHouse client 以 try/finally 關閉 |

## 7.27 回寫（8f1ce7a）

四項與程式逐一相符：`render_llm_section(a, b, pairs)` 由 main 附在 `render_markdown` 後；kappa 整數運算、全同類 1.0；延遲線性內插與 CSV 欄位順序；標註者由 `LABEL_PRIMARY`＋`build_labeler` 推出、百分比與三位小數。只在「比較」表後新增一段，未動同節其他處，符合追加指示。

## 測試

驗收測試以預寫資料驗證全部指標的預期值（一致率 4/7、kappa 12/33、各看板、延遲 21 篇 p50 11／p95 20、信心分布、CSV、main 端到端）；qa 實跑 347 passed。worker 單元測試涵蓋正常、空輸入、邊界（門檻含等於、單值百分位、全同類 kappa）、注入字串。

## 非阻擋建議（可另開 issue，不影響本次判定）

- `src/radar/ml/training/compare.py:352`、`:355` — `--a`／`--b` 未驗證就組進輸出路徑（`models/<b>/`、`disagreements-<a>-vs-<b>.csv`）。只有本機操作者自己執行，不跨權限邊界；但 7.27 威脅表已限 `model_version` 格式，可在 main 用 `import_model.MODEL_VERSION_RE` 檢查兩個參數（baseline 的 `tfidf-lr-<時間>` 也符合）
- `src/radar/ml/training/compare.py:33-34` — polarity 與 score 各自 `argMax(..., predicted_at)`，同一版本同一篇 `predicted_at` 相同的兩筆時可能取自不同列；可改 `argMax(tuple(polarity, arrayMax(mapValues(scores))), predicted_at)`。實務上同版本重算結果相同，影響極小
