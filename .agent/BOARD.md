# 布告欄

<!-- 只放目前這一階段；只有 manager 透過 ae board 修改；階段完成時整份封存到 .agent/tasks/<tag>.md -->

> 上一階段：`.agent/tasks/v0.8.2.md`（派工單在 `.agent/tasks/v0.8.2/`）

## 目標與範圍

- 本輪：v0.9.0 PTT BBS 即時資料來源 spike（#57）＋補實驗（D-048）：實測 1 條連線輪流讀 4 篇的延遲與同帳號同時連線數，產出最終導入建議
- 不做：導入 BBS collector、改動現有爬蟲與管線；階段 9 上雲；多天驗收（D-031）；所有熱門文章都 1 分鐘內（需多帳號）；#308 #310 #311 #314 #315 等 backlog 小項
- 驗收條件：
  - 調查報告涵蓋站規與停權風險、同帳號同時登入數與 3 個爬蟲的分工方式、相依套件比較、推文資料與現有 raw.posts 的對應
  - 用甲方的專用小號做一次性、低頻率的手動實驗，量到熱門文章新推文從出現到被讀到的延遲 p50，並與網頁版比較；實驗不進測試流程，自動化測試仍不連真實 PTT
  - 帳密只放 .env，文件、程式與 log 只有變數名稱，不出現帳密的值
  - 報告依門檻（熱門文章新推文 p50 在 1 分鐘內）給出導入或不導入的明確建議；導入與否由甲方決定
  - 補實驗在晚間 20:00～23:00 跑，4 篇都符合選取規則；P2 輪流讀 4 篇，樣本 ≥ 100 則且來自 ≥ 3 篇，量到 p50 並與網頁版比較
  - 實測同帳號同時連線數（不踢線、出現警告即停，D-049），報告依結果重算需要的連線數
  - 實驗工具先修好 ledger 誤刪（資安 O-2）與門檻判定排除不符選取規則的文章（UAT F-1）
  - 報告更新為最終建議，導入與否由甲方決定
  - v0.9.0 甲方驗收清單 PASS（docs/uat/v0.9.0.md，只列 agent 驗不到的項目）

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
| 2026-11-06 | D-043 | BBS spike 用 PyPtt ==2.3.16，只放 bbs-spike group |
| 2026-11-06 | D-044 | 不實測同時登入數，報告以 1 條連線計算 |
| 2026-11-06 | D-045 | 跑實驗前甲方先讀站規與目標看板板規；明文禁止就不做並改範圍 |
| 2026-11-09 | D-046 | PTT_BBS_USERNAME／PASSWORD 改必填（取消註解），讓 check-env 檢查 |
| 2026-11-09 | D-047 | BBS spike 照跑；報告另評估混合方案（BBS 只顧前 N 篇，其餘網頁版） |
| 2026-11-09 | D-048 | BBS spike 補做實驗（範圍另行盤問） |
| 2026-11-09 | D-049 | 補實驗實測同帳號同時連線數（取代 D-044），不踢線、警告即停 |

## 任務狀態

| 任務 | 負責 | 狀態 | 嘗試 | 驗收證據 |
|---|---|---|---|---|
| bbs-spike-design | architect | done | 0 | PR #318 |
| bbs-spike-tool | backend | done | 1 | PR #324 |
| bbs-hot-articles-stat | backend | done | 0 | 統計完成（作廢 PR），.agent/reports/bbs-hot-articles-stat.json |
| gitleaks-test-sentinel | architect | done | 0 | PR #323 |
| bbs-spike-report | backend | done | 1 | PR #326 |
| bbs-retest-design | architect | todo | 0 |  |

## 卡住／待甲方決定

- 待甲方決定 D-050、D-051；bbs-retest-design（PR #331）待核可

## 注意事項（踩過的坑）

- （無）
