# <專案名稱>

<!-- manager 維護。給第一次打開專案的人看：這是什麼、怎麼跑起來、現在做到哪 -->

一句話說明這個專案做什麼、給誰用。

## 快速開始

1. 設定：在自己的終端機（不是 agent 的 sandbox）跑 `python3 scripts/check_env.py`，依提示在 `.env` 填入缺少的值，填完再跑一次；之後 `.env.example` 有變也要重跑
2. 安裝：
3. 啟動：（用到 docker 的每個指令都寫成單獨一行 `docker compose …`，不包進 make 或 script、不跟 `cd`、`&&` 寫在一起：agent 的 sandbox 只認這個形式，甲方與 uat 才會跑同一條指令）
4. 檢查：`make check`

## 功能

| 功能 | 版本 | 說明 |
|---|---|---|

## 架構

| 目錄 | 用途 |
|---|---|

## 開發方式

由 agent 團隊開發（規則見 `CLAUDE.md`）。分支：`main` ← `develop` ← `feat/…`、`fix/…`；每個階段合回 `main` 並打 tag。
決策紀錄：`docs/decisions.md`；使用者測試：`docs/uat/`。

## 版本

| 版本 | 日期 | 內容 |
|---|---|---|
