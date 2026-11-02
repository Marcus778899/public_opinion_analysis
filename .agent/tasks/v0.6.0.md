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
| v060-security | security | done | 0 | docs/security/v0.6.0.md PASS bd11330（H-1 已修；M ×3、L ×4 皆已處置：D-010、D-011、#68～#71、#79） |
| v060-uat | uat | done | 0 | docs/uat/v0.6.0.md 甲方驗收：PASS（23 項全勾）；警示重放紀錄；minor #65～#67、#80～#82 |
| spec-release-order | architect | done | 0 | PR #74 |
| bot-forbidden-crash | backend | done | 0 | PR #75 |
| ci-gitleaks-ignore | backend | done | 0 | PR #77 |

## 卡住／待甲方決定

- （無）

## 注意事項（踩過的坑）

- （無）
