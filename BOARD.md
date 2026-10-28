# 布告欄

<!-- 只放目前這一階段；只有 manager 透過 scripts/board.py 修改；階段完成時整份封存到 tasks/<tag>.md -->

> 上一階段：`tasks/v0.8.0.md`（派工單在 `tasks/v0.8.0/`）

## 目標與範圍

- 本輪：BERT 進 shadow：開發規格 7.27「評估結果與進 shadow 的調整」順序 3～6（候選 ckip fp32，#178）
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
| 2026-10-21 | D-020 | 推論套件 onnxruntime＋tokenizers |
| 2026-10-21 | D-021 | 預訓練模型 ckiplab 與 hfl macbert 各訓一版比較（接受 GPL，不對外散布） |
| 2026-10-21 | D-022 | Colab 端 torch、transformers、optimum |
| 2026-10-21 | D-023 | shadow 上限 2 CPU、1.5g、INFERENCE_THREADS=2 |
| 2026-10-21 | D-024 | 訓練資料只在 Colab 工作階段上傳 |
| 2026-10-22 | D-025 | ckiplab 釘 safetensors 轉換 PR；macbert 載 .bin 要求 torch>=2.6、釘 revision |
| 2026-10-25 | D-026 | gitleaks 對 generic-api-key 放行 rev/sha 變數名＋40 位小寫 hex（不逐筆忽略） |
| 2026-10-26 | D-027 | v0.8.0 先發版；模型驗收（Colab、shadow 3 天、compare）改由 #178 追蹤 |
| 2026-10-27 | D-028 | 推文立場分類先不做，列 backlog #181（D-029、D-030 延到設計時） |

## 任務狀態

| 任務 | 負責 | 狀態 | 嘗試 | 驗收證據 |
|---|---|---|---|---|

## 卡住／待甲方決定

- v0.8.0 待甲方驗收（README 階段 8 小節）
- BERT 進 shadow 順序 1、2 已合併（#195、#197）；待甲方重跑 ckip fp32 evaluate（順序 3）
- 待甲方重跑 ckip fp32 evaluate（7.27 順序 3）

## 注意事項（踩過的坑）

- （無）
