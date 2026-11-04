PASS cc653aa

# QA gap-record-update

## 驗收條件
1. 7.29 第 10 列、標題日期延到 10-30：通過。標題 `2026-10-08～10-30`；第 10 列 `10-30 04:05 → 07:15 | 3.2 h | 原因`，4 欄與前 9 列相同（# / 區間（UTC） / 長度 / 原因），時間為 UTC，用 `→`，長度用 `h`。
2. 說明行：通過。新增 bullet「區間 10 的告警」，寫明 watchdog 05:06 記 ERROR、休眠中沒網路所以 `/fail` 沒送出、恢復後 6 則警示失真（7.20 已知限制，#264）。與調查回報第 4、5 節一致。
3. 數字以調查回報為準並附出處：通過。對照 reports/comments-cdc-gap-investigate.json：
   - 起點 04:05（posts 最後變更 04:05:08Z；PG 最後寫入 04:05:06Z），恢復 07:15（07:15:10Z）。04:05:08 → 07:15:10 = 3 h 10 m = 3.17 h，約 3.2 h，吻合。
   - pmset：04:04:19Z 起合蓋，07:20:34Z 開蓋，與列中「04:04Z 起合蓋、07:20Z 開蓋」一致。
   - 「Debezium 從上次 LSN 續跑」「PG 與 ClickHouse 的 posts 一致」：回報第 1 節（LSN 3/F54E30A8；posts 21200 對 21200）。
   - 出處已寫在該列（`reports/comments-cdc-gap-investigate.json`）。

## 範圍
`git diff develop...HEAD --stat`：只有 docs/development-spec.md，3 增 1 刪；變更全在 7.29（標題 1 行、新列 1 行、新 bullet 1 行）。其他章節、程式沒動。worktree 乾淨（git status 無輸出）。

## 驗證指令（自行執行）
pre-commit run --files docs/development-spec.md
trim trailing whitespace...Passed
fix end of files...Passed
check yaml...Skipped
ruff (legacy alias)...Skipped
ruff format...Passed
bandit...Skipped
exit=0

## 其他觀察（不構成 FAIL）
- 禁區內未改的 development-spec.md 第 373、1678 行仍寫「10-08～10-29 的缺口」，與 7.29 新標題範圍不同；manager 可決定是否另單同步。
- 無寫死設定值（純文件）。
