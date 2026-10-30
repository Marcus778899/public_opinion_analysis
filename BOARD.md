# 布告欄

<!-- 只放目前這一階段；只有 manager 透過 scripts/board.py 修改；階段完成時整份封存到 tasks/<tag>.md -->

> 上一階段：`tasks/v0.8.0.md`（派工單在 `tasks/v0.8.0/`）

## 目標與範圍

- 本輪：處理 backlog 小項後發 v0.8.1（階段 9 暫緩）：第 3 批剩 #80、#254（D-035）
- 不做：階段 9 上雲；#57（v0.8.1 發版後討論）；#68 #69 #251；多天驗收（D-031）；#178 #181

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

## 任務狀態

| 任務 | 負責 | 狀態 | 嘗試 | 驗收證據 |
|---|---|---|---|---|
| bert-shadow-gate-ruling | architect | done | 0 | PR #200 |
| shadow-restart-investigate | backend | done | 0 | reports/shadow-restart-investigate.json（只調查，已作廢 PR） |
| bert-derive-max-len | backend | done | 0 | PR #203 |
| shadow-memory-measure | backend | done | 0 | reports/shadow-memory-measure.json（只量測，已作廢 PR） |
| bert-batch-tokens-default | backend | done | 0 | PR #206 |
| comment-year-infer | backend | done | 0 | PR #211 |
| consumer-commit-wait | backend | done | 0 | PR #210 |
| gossiping-gap-investigate | backend | done | 0 | reports/gossiping-gap-investigate.json（只調查，已作廢 PR） |
| init-exit-code | backend | done | 0 | PR #213（只加回歸測試，255 無法重現） |
| ml-cli-usability | backend | done | 0 | PR #216 |
| shadow-missing-model-exit | backend | done | 0 | PR #217 |
| comment-time-recrawl | backend | done | 0 | PR #220（剩 10 則在 3 篇已刪文，接受） |
| pipeline-gap-design | architect | done | 0 | PR #221 |
| crawl-backfill-depth | backend | done | 0 | PR #225（e2e 新測試待發版前在 e2e 環境實跑） |
| pipeline-stall-alert | backend | done | 0 | PR #224 |
| crawl-backfill-retry | backend | done | 0 | PR #230 |
| kafka-version-upgrade | backend | done | 0 | PR #229；開發環境三台已逐台升 4.1.2，無 under-replicated |
| import-model-hardening | backend | done | 0 | PR #233 |
| scheduler-statement-timeout | backend | done | 0 | PR #239 |
| bot-poll-resilience | backend | done | 0 | PR #242 |
| ci-tool-checksum | backend | done | 0 | PR #238 |
| gitleaks-allowlist-boundary | backend | done | 0 | PR #241 |
| spec-docs-sync | backend | done | 1 | PR #246 |
| bot-push-allowlist | backend | done | 0 | PR #247 |
| grafana-readonly-verify | backend | done | 0 | PR #249（權限已夠緊；收斂權限另開 #251） |
| subscription-toggle-latency | backend | done | 0 | PR #250（Telegram 往返待部署後從 bot log 實測） |
| secret-placeholder-guard | backend | done | 0 | PR #253 |
| infra-secret-guard | backend | done | 0 | PR #256 |
| heat-replay-align | backend | done | 0 | PR #258 |
| comments-cdc-gap-investigate | backend | done | 0 | reports/comments-cdc-gap-investigate.json（開發機休眠，非程式問題；watchdog 有記 ERROR） |
| replay-alert-repro | backend | done | 1 | PR #265 |

## 卡住／待甲方決定

- 發版前在 e2e 環境跑 test_crawler_restart_backfills_more_than_three_pages（#225 未實跑）
- 發版前：部署後從 bot log（callback step=…ms=）取 #82 各步驟實測，甲方親手點「我的訂閱」確認 2 秒內

## 注意事項（踩過的坑）

- （無）
