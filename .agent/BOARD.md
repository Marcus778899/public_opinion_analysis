# 布告欄

<!-- 只放目前這一階段；只有 manager 透過 ae board 修改；階段完成時整份封存到 .agent/tasks/<tag>.md -->

> 上一階段：`.agent/tasks/v0.8.1.md`（派工單在 `.agent/tasks/v0.8.1/`）

## 目標與範圍

- 本輪：v0.8.2 穩定性小版（D-042）：#281 producer fatal 後結束程式交給 restart；#282 Connect 內部 topic 改 2 份副本（D-041）與 connect 健康檢查；#289 推論 2 CPU、2g、INFERENCE_THREADS=2；#262 init 遇 task FAILED 先重啟；#268 未來時間不讓補抓失效；小項 #276 #263 #270 #277 #269、#271 剩下兩項
- 不做：#264 #259 #251 #68 #69 #57 #178 #181；階段 9 上雲；多天驗收（D-031）
- 驗收條件：
  - 模擬 producer 進入 fatal 狀態，服務記 CRITICAL 並結束，被 docker 自動重啟後恢復送訊息
  - Connect 內部 topic 都是 2 份副本；停掉任一台 broker，connect 照樣啟動且 connector 還在；connect 健康檢查會發現 connector 不存在
  - 推論容器有 CPU 與記憶體上限，在上限內補完積壓、沒有因記憶體不足被砍
  - 重建 postgres 後跑一次 init 就成功，不用重跑
  - PTT 標頭是未來時間時，補抓不會停掉（有測試）
  - 小項 #276 #263 #270 #277 #269 與 #271 剩下兩項完成，CI 綠燈
  - v0.8.2 甲方驗收清單 PASS（docs/uat/v0.8.2.md，只列 agent 驗不到的項目）

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
| 2026-10-29 | D-031 | 多天驗收（階段 5 的 3 天、shadow 3 天＋compare、階段 9 的 7 天）往後擺，上雲後一起跑；階段 9 不等 3 天驗收 |
| 2026-10-29 | D-032 | 停機漏抓的文章不補，開發規格記缺口日期 |
| 2026-10-29 | D-033 | 未來時間推文所屬 55 篇重爬，依新規則覆寫 |
| 2026-10-29 | D-034 | Kafka 升到 4.1.2（修 KAFKA-19888 停擺） |
| 2026-10-29 | D-035 | #254 排進 v0.8.1（基礎服務擋範例密碼、PG port 綁本機） |
| 2026-11-02 | D-036 | CI 用 fine-grained token（repo secret AE_TOKEN，唯讀）取得 agent-engineering |
| 2026-11-02 | D-037 | agent-v1-cleanup 仲裁後狀態卡住由甲方處理工具，不用空 commit 繞過 |
| 2026-11-04 | D-038 | 遺留 heat-replay-* 的 group 與內部 topic 清掉（v0.8.1） |
| 2026-11-04 | D-039 | Kafka 三個對外 port 改綁 127.0.0.1（v0.8.1） |
| 2026-11-04 | D-040 | 正式推論直接換 bert-ckip-202610280849，shadow 不開；#178 上雲後驗證 |
| 2026-11-04 | D-041 | Connect 內部 topic 改 2 份副本（#282） |
| 2026-11-04 | D-042 | v0.8.2 穩定性小版範圍（#281 #282 #289 #262 #268＋小項） |

## 任務狀態

| 任務 | 負責 | 狀態 | 嘗試 | 驗收證據 |
|---|---|---|---|---|
| stability-design | architect | done | 0 | PR #292 |
| producer-fatal-exit | backend | done | 0 | PR #298 |
| connect-resilience | backend | done | 0 | PR #296 |
| cli-wording-sha256 | backend | done | 1 | PR #297 |
| backfill-since-filename | backend | done | 0 | PR #302 |
| ci-token-order | backend | done | 0 | PR #301 |
| inference-resource-limit | backend | done | 0 | PR #304 |
| heat-alert-dup-investigate | backend | done | 0 | 調查完成（作廢 PR），.agent/reports/heat-alert-dup-investigate.json |
| connect-rf-reassign | backend | done | 0 | 操作完成（作廢 PR），.agent/reports/connect-rf-reassign.json |
| stability-dev-verify | backend | done | 0 | 開發環境驗證完成（作廢 PR），.agent/reports/stability-dev-verify.json |

## 卡住／待甲方決定

- v0.8.2 甲方驗收清單（docs/uat/v0.8.2.md）：make e2e 已 PASS（13 passed）；待甲方驗 Grafana、Telegram、模型重匯後寫 甲方驗收：PASS

## 注意事項（踩過的坑）

- （無）
