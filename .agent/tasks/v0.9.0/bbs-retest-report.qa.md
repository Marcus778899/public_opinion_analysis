PASS 4fbc17a

# bbs-retest-report 驗證證據（PR #337）

## 驗證指令與結果

- `make check`（在 `.worktrees/bbs-retest-report`）：`2237 passed in 147.83s`，exit 0（自己跑，非引用回報）
- `wc -l docs/reports/bbs-spike.md`：145，未超過 200
- `grep -rniE "PTT_BBS_(USERNAME|PASSWORD)=." docs`：只命中 `docs/uat/v0.9.0.md:15`。內容是 S4 項目裡寫的 grep 指令文字（`grep PTT_BBS_(USERNAME\|PASSWORD)=.`）與 PASS 說明，沒有帳密值，也不是本單檔案、本單 diff 沒動它。依 manager 補充不算 FAIL。
- 本單 diff 內加上的行沒有 password、密碼字樣；報告沒有 PTT 文章檔名、使用者 ID 或推文內容。
- `grep -rn "TODO(bbs-retest-report)" src tests`：無結果。
- 改動檔案只有 `docs/reports/bbs-spike.md`、`docs/development-spec.md`，都在負責檔案內。

## 數字對照原始檔（data/spike/bbs-retest/20261110T124120Z/，自己用 python 重算）

- R2 事件 207 則，分布 102／37／37／31（4 篇）；p50(`E`) 52.69 秒，與報告「52.7」相符
- 網頁版與 summary.json：p50(`E`) 315.11、配對差 262.83、時鐘偏差 0.43，相符
- reads.jsonl：R2 82 次全成功，平均 5.247 秒；M 32 次全成功；全程 114 次平均 5.344 秒；每篇 R2 約 20～21 次，相符
- `N_max` = ⌊120÷(5.25+22.5)⌋ = 4；⌈33÷4⌉ = 9；4×3÷33 = 36%（summary.json 0.3636），相符
- ledger.jsonl：A 12:41、B 13:21、C 13:31（UTC）全 ok，間隔 ≥ 10 分；第一次 ledger 2 次，累計 5 次，相符
- R2 時間 12:41:39～13:21:23，約 40 分鐘，相符；M 到 13:32

## 驗收條件逐條

1. 第一行為最終建議（混合方案、前 4×k 篇、導入前甲方確認站規、決定歸甲方）：符合
2. 「補實驗」一節含 R1／R2／R3 判定與數字、網頁版比較、`N_max`、全量 9 條、36%、k=3 為推算的限制；145 行：符合
3. 連線數重算並寫明口徑（R2 平均，全程平均附註）：符合
4. 第一次實驗段落保留，矛盾句改為引用補實驗（第 1、4、7 節）：符合
5. 7.31 G 結論與「後續階段」13 已補，並引用報告：符合

## 小觀察（不構成 FAIL）

- 報告寫「M 階段 A、B 的讀取都成功」，但 reads.jsonl 沒有 conn 欄位，無法從原始檔區分是哪條連線讀的；此句靠 manager 背景（沒被踢）推得，不是原始檔直接證據。
- worker 回報的 open_questions 都已如實反映在報告中（網頁版失敗看不出來、樣本偏重 1 篇、5.25 秒原因未查）。
