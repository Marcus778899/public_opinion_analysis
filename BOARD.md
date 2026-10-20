# 布告欄

<!-- 只放目前這一階段；只有 manager 透過 scripts/board.py 修改；階段完成時整份封存到 tasks/<tag>.md -->

## 目標與範圍

- 本輪：發版 v0.6.0（階段 1～6 develop → main：security 審查、uat、甲方驗收）；之後開始階段 7 Dashboard
- 不做：階段 3 Stock 重新標註、階段 5 的 3 天驗收（照開發規格第 6 章之後再做）

## 已定案決策（細節見 docs/decisions.md；要改先問甲方）

| 日期 | 編號 | 決策 |
|---|---|---|
| 2026-10-20 | D-003 | semver；階段 1～6 以 v0.6.0 合進 main，不等階段 3、5 驗收；stage-3～6 tag 不補打 |
| 2026-10-20 | D-009 | .env.example 的選填設定寫成註解，check_env 不再當必填 |
| 2026-10-20 | D-011 | 維持放行 docker compose *，接受 M-3 風險 |
| 2026-10-20 | D-008 | 修上游範本：check_env 戳記取代讀 .env；修好前甲方代開單 |
| 2026-10-20 | D-010 | bot 允許清單沒設就啟動失敗，開放所有人須 TELEGRAM_ALLOW_ALL=true（v0.7.0） |
| 2026-10-20 | D-012 | 本機 .git/info/exclude 加 .venv；上游範本 .gitignore 不加斜線 |

## 任務狀態

| 任務 | 負責 | 狀態 | 嘗試 | 驗收證據 |
|---|---|---|---|---|
| v060-security | security | blocked | 0 | docs/security/v0.6.0.md FAIL fac0421：high 1（H-1 → bot-forbidden-crash）、medium 3（M-1 D-010、M-2 #68、M-3 D-011）、low 3（#69～#71） |
| v060-uat | uat | review | 0 | docs/uat/v0.6.0.md：blocker 0、major 0、minor 4（F-1、F-2 README 已補；#65～#67 backlog）；甲方驗收清單 24 項待勾 |
| spec-release-order | architect | qa | 0 | PR #74 |
| bot-forbidden-crash | backend | qa | 0 | PR #75 |

## 卡住／待甲方決定

- v0.6.0 資安 FAIL（H-1）：修正中（bot-forbidden-crash #73），合併後重審

## 注意事項（踩過的坑）

- （無）
