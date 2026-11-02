PASS 86b0934

# 驗證證據 dashboard-var-test-hardening（第二輪）

## 實際執行
- `gh pr checks 143 --watch`（等到結束）：Check pass 42s、Integration Test pass 2m25s、Security pass 25s（皆為 commit 86b0934 的 run）
- `make check`（worktree 內）：`1134 passed in 3.24s`
- `docker compose ls`：無其他堆疊；`docker compose --env-file .env -f .worktrees/dashboard-var-test-hardening/compose.yaml run --rm test`：`330 passed in 42.74s`；已 `down -v`（容器、volume、network 全移除）
- `grep -rn "TODO(dashboard-var" src tests`：無結果；worktree `git status --short` 乾淨

## 上一輪問題 1（in_string 只認單引號）
我用一次性腳本直接呼叫 `references()`，結果：
- `a="${board:percentencode}"` -> in_string False
- ``a=`${board:percentencode}` `` -> False
- `c=${board:percentencode}`（引號外）-> False
- `x='${board:percentencode}'` -> True
- `x='a\'b ${board:percentencode}'`（單引號內含跳脫）-> True（引號內內容仍被正確略過）
- `x="it's" AND y='${board:percentencode}'`（雙引號內含單引號）-> True（單引號不會誤開字串）
- `x='"' AND y=${board:percentencode}`（單引號內含雙引號）-> False
新增 `test_references_helper_counts_only_single_quotes_as_in_string` 涵蓋雙引號、反引號、引號外各一例與單引號正例，且包含在 330 通過內。

## 逐條驗收
1. 兩個 percentencode 測試斷言 `in_string`：通過（diff 確認，現行 dashboard 通過）。
2. P_VOLUME 改看 labels：`panel_text` 讀欄名＋labels＋值，並有 `mine.board in text` 正向斷言；通過。（未做反向混入實驗，推演成立，不列問題。）
3. docstring、`_dash.references` docstring、開發規格 7.25 都寫「percentencode 且在單引號內」，與實作一致：通過。
4. compose 測試全過並 `down -v`：通過。
5. `make check` 通過、PR CI 全綠：通過。

## 其他檢查
- 寫死設定值：diff 內無 port、網址、token 新增。
- 未動 `src/`、`infra/grafana/`、`scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`；未新增攻擊字串測試（D-017）。

## 問題（共 0 個）
