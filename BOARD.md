# 布告欄

<!-- 只放目前這一階段；只有 manager 透過 scripts/board.py 修改；階段完成時整份封存到 tasks/<tag>.md -->

## 目標與範圍

- 本輪：發版 v0.6.0（階段 1～6 develop → main：security 審查、uat、甲方驗收）；之後開始階段 7 Dashboard
- 不做：階段 3 Stock 重新標註、階段 5 的 3 天驗收（照開發規格第 6 章之後再做）

## 已定案決策（細節見 docs/decisions.md；要改先問甲方）

| 日期 | 編號 | 決策 |
|---|---|---|
| 2026-10-20 | D-003 | semver；階段 1～6 以 v0.6.0 合進 main，不等階段 3、5 驗收；stage-3～6 tag 不補打 |

## 任務狀態

| 任務 | 負責 | 狀態 | 嘗試 | 驗收證據 |
|---|---|---|---|---|
| v060-security | security | blocked | 0 | docs/security/v0.6.0.md FAIL fac0421：high 1（H-1 → bot-forbidden-crash）、medium 3（M-1 D-010、M-2 #68、M-3 D-011）、low 3（#69～#71） |
| v060-uat | uat | review | 0 | docs/uat/v0.6.0.md：blocker 0、major 0、minor 4（F-1、F-2 README 已補；#65～#67 backlog）；甲方驗收清單 24 項待勾 |
| spec-release-order | architect | blocked | 0 |  |
| bot-forbidden-crash | backend | blocked | 0 |  |

## 卡住／待甲方決定

- D-008：task.py new 在 sandbox 讀不到 .env 而當掉，所有派工單（spec-release-order、階段 7）卡住
- D-009：.env.example 的 OPENROUTER_API_KEY、API_CORS_ORIGINS 是選填卻被當必填，task.py new 拒絕開單
- v0.6.0 資安 FAIL（H-1）：修正單 bot-forbidden-crash 待開（同樣卡在 D-008、D-009）

## 注意事項（踩過的坑）

- （無）
