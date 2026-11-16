PASS 9f22e9f

# QA bbs-spike-report（PR #326，第 3 輪）

## 指令與結果
- `grep -rniE "PTT_BBS_(USERNAME|PASSWORD)=." docs`（worktree）：無結果（rc=1）
- `pre-commit run --files docs/reports/bbs-spike.md docs/development-spec.md`：Passed（其餘 Skipped）
- 報告 115 行（≤150）；第 1 行為「建議不導入」；8 段齊全；diff 只動兩個負責檔；無帳密、使用者 ID、推文內容
- 重算 reads.jsonl：81 筆全程平均 7.89、P2 61 筆 7.125，與報告第 1 節口徑註記一致（採 P2 7.1 秒：N_max=4、9 條；全程 7.9 秒：N_max=3、11 條，已附註）
- 上輪數字（p0、P1/P2/網頁版 p50、110 則拆解 68+38+4、35=24+11 等）維持相符

## 前輪問題複驗
1. 讀取口徑：已寫明並附另一口徑，混合方案與 N=3 附註一致 -> 已修
2. 第一行建議：已修
3. review 必改（門檻 1 統一為「部分證實」、7.31 結論同步、IP 事實／觀察／評估、第 7、8 節）：已修，報告與規格無矛盾

## 問題
無。#327（summary.json 口徑）已另開 backlog，不列入。
