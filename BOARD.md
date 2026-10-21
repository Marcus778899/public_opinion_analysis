# 布告欄

<!-- 只放目前這一階段；只有 manager 透過 scripts/board.py 修改；階段完成時整份封存到 tasks/<tag>.md -->

> 上一階段：`tasks/backlog-cleanup-2026-10.md`（派工單在 `tasks/backlog-cleanup-2026-10/`）

## 目標與範圍

- 本輪：v0.8.0 階段 8 BERT 與 shadow 比較：S8-01 fine-tune 中文 BERT（D-019：agent 備 notebook／匯出，甲方跑訓練）、S8-02 新 model_version 並行推論、S8-03 ClickHouse 比較兩版（macro-F1、不一致文章、延遲）；驗收見開發規格階段 8；另：gitleaks 封存根治（D-018）
- 不做：上雲（階段 9）；backlog 其餘 issue

## 已定案決策（細節見 docs/decisions.md；要改先問甲方）

| 日期 | 編號 | 決策 |
|---|---|---|
| 2026-10-20 | D-003 | semver；階段 1～6 以 v0.6.0 合進 main，不等階段 3、5 驗收；stage-3～6 tag 不補打 |
| 2026-10-20 | D-009 | .env.example 的選填設定寫成註解，check_env 不再當必填 |
| 2026-10-20 | D-011 | 維持放行 docker compose *，接受 M-3 風險 |
| 2026-10-20 | D-008 | 修上游範本：check_env 戳記取代讀 .env；修好前甲方代開單 |
| 2026-10-20 | D-010 | bot 允許清單沒設就啟動失敗，開放所有人須 TELEGRAM_ALLOW_ALL=true（v0.7.0） |
| 2026-10-20 | D-012 | 本機 .git/info/exclude 加 .venv；上游範本 .gitignore 不加斜線 |
| 2026-10-20 | D-013 | worktree 用 sparse-checkout 排除 .claude/、.mcp.json、.vscode/（上游範本已修） |
| 2026-10-20 | D-014 | 階段 7 全用 Grafana；自建 web 前端延到階段 9 |
| 2026-10-20 | D-015 | CI 加速加 pytest-xdist，不用付費 runner |
| 2026-10-20 | D-016 | qa 也可以跑 docker compose |
| 2026-10-21 | D-017 | Dashboard 變數一律 percentencode 由 ClickHouse 解碼；驗收只做靜態＋正常值，不用攻擊字串 |
| 2026-10-21 | D-018 | gitleaks 不掃 tasks/ 封存，改設定根治（不再逐筆加忽略） |
| 2026-10-21 | D-019 | 階段 8：agent 準備 notebook／匯出／評估，甲方在 Colab 跑 fine-tune |

## 任務狀態

| 任務 | 負責 | 狀態 | 嘗試 | 驗收證據 |
|---|---|---|---|---|
| gitleaks-cleanup-archive-ignore | backend | done | 0 | PR #150 |
| bert-design | architect | qa | 0 |  |
| gitleaks-archive-allowlist | backend | done | 0 | PR #153 |

## 卡住／待甲方決定

- 待甲方決定 D-020～D-024（階段 8 套件、預訓練模型、notebook 套件、shadow 資源、資料上傳平台）

## 注意事項（踩過的坑）

- （無）
