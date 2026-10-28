PASS 5009f7b

# dashboard-integration 驗證（第 3 輪，commit 5009f7b）

## 結論

7d27217 之後只有一個 commit（5009f7b），只改 `docs/development-spec.md`（3 行）。review 退回的 3 點都已改好且與實作一致；make check 重跑全過；PR #109 head 5009f7b 的 CI 全綠。程式與測試沒變，沿用第 2 輪實跑證據（下方保留）。本輪 0 個問題。

## 本輪實測

| 項目 | 結果 |
|---|---|
| 變更範圍 | `git log 7d27217..HEAD`：僅 5009f7b；`git diff --stat 7d27217 HEAD`：`docs/development-spec.md | 6 +++---`，無程式、測試、設定變動 |
| 1048 行 | 已改為：`$__timeFilter_ms`、`$__timeInterval` 由本單經 `/api/ds/query` 驗證；`$board`、`$min_score` 前端代換，整合測試依假設格式模擬，真前端展開由 uat 確認。與 `_dash.expand_vars` 模擬的實況及 review 建議文字一致 |
| 1093 行（派工順序第 4 列） | 「以 make up 截圖」已改為「畫面截圖與真前端的變數展開由階段收尾的 uat 做（實際分工：qa 寫測試，backend 修設定與文件）」，與 364 行進度表、派工單一致 |
| 1173 行（radar DB 列） | 已改為使用者有 cdc 模組與 dashboard 整合測試（同組 shared_radar_db），acceptance/dashboard 沒分組有被 TRUNCATE 風險（已鎖定，另開單由 qa 補標）。核對 acceptance/dashboard/test_panels.py:7、test_views.py:4 確實寫「不需要 xdist_group」，文件描述屬實 |
| make check | pre-commit 全過；`1110 passed in 4.37s` |
| PR #109 CI（head 5009f7b4f4fc，與本地 HEAD 一致） | `gh pr checks 109`：Check pass 45s、Integration Test pass 2m10s、Security pass 34s |
| worktree | `git status` 乾淨 |

## 第 2 輪證據（程式未變，沿用）

- 全新堆疊（down -v）compose test：`309 passed in 58.65s`；同堆疊第 2 次 `309 passed in 56.48s`；`pytest tests/integration -n 0`：`309 passed in 137.91s`
- 錯誤密碼連 12 次皆 401、之後正確密碼 200；開發環境 infra/ 無 diff、無 BRUTE 旗標
- 唯讀帳號：CREATE／TRUNCATE 164；max_execution_time=61 回 452、=30 可用；readonly=0 回 164；僅見 radar 資料庫
- 寫死設定：新增項目只有測試 compose 內的旗標

## 未驗證／限制

- 真前端的 `$board`、`$min_score` 展開（多選、All、含單引號、沒有看板）與畫面截圖：待階段收尾 uat
- acceptance/dashboard 未標 xdist_group 的潛在 flake：已鎖定，須另開單給 qa
- Kafka 偶發 UNKNOWN_TOPIC_OR_PART：backlog #110
