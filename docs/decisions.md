# 決策紀錄

需要甲方決定的事都在這裡，由 manager 維護。流程：agent 提問 → manager 寫進「待決定」→ 甲方回覆 → manager 移到「已決定」。
其他文件一律用編號引用（例：見 D-003），不重寫內容。

## 待決定

<!-- 範本：
### D-001 一句話問題
- 背景：為什麼要決定（1–2 行）
- 選項：A. … ／ B. …
- 建議：A，理由一行
- 提出：architect（todo-design）
-->

## 已決定

<!-- 範本：
### D-001 一句話問題
- 決定：A. …
- 理由：一行
- 影響：docs/contracts/todos.md §2、BE-01
- 日期：YYYY-MM-DD
-->

### D-001 導入 agent 團隊流程後，「骨架 → 停下確認 → 實作」的兩輪規則怎麼對應
- 決定：設計 PR（契約、骨架、驗收測試目錄）由甲方 `pr.py approve` 一次就是第一輪；實作單不再停下等甲方
- 日期：2026-10-20

### D-002 功能分支怎麼跟上 develop
- 決定：一律 `pr.py sync`（把 develop 併進分支），不 rebase、不 force push
- 日期：2026-10-20

### D-003 版本名稱
- 決定：用 semver，由 `release.py` 發版。階段 1～6 的成果以 `v0.6.0` 合進 `main`，不再等階段 3、5 驗收；之後每個階段一版（階段 7 = `v0.7.0`）。`stage-3`～`stage-6` tag 不補打，由 `v0.6.0` 涵蓋。階段 3 的 Stock 重新標註、階段 5 的 3 天驗收仍照開發規格第 6 章「執行順序」，之後再做
- 理由：main 停在階段 2 太久；兩項待驗收不影響其他階段發版
- 影響：開發規格第 6 章「執行順序」（派工單 `spec-release-order`）
- 日期：2026-10-20（同日修訂：原為等階段 3、5 驗收通過後才合進 main）

### D-004 開發規格第 6 章與進度
- 決定：第 6 章保留各階段範圍與驗收標準，作為 architect 的需求來源；進度表凍結在階段 6，之後進度只看 BOARD.md 與派工單；`TODO(...)` 標記改用 task_id
- 日期：2026-10-20

### D-005 需要外部 API 的工作
- 決定：sandbox 開放 `api.groq.com`、`api.telegram.org`、`www.ptt.cc`、`slack.com`、`hc-ping.com`，agent 可以自己跑；測試仍不可對真實 PTT 發請求
- 日期：2026-10-20

### D-006 專案自己的營運腳本放哪
- 決定：從 `scripts/` 搬到 `tools/`；`scripts/` 歸範本流程腳本（`update.sh` 會整個覆蓋）
- 日期：2026-10-20

### D-007 覆蓋率關卡需要的相依
- 決定：`pytest-cov` 加進 dev 群組（不進 production image）；`diff-cover` 只在 CI 裡 pip 安裝
- 日期：2026-10-20

### D-009 `.env.example` 把選填設定當成必填，`task.py new` 拒絕開單
- 決定：A. 選填設定在 `.env.example` 寫成註解（`GEMINI_API_KEY`、`OPENROUTER_API_KEY`、`API_CORS_ORIGINS`），甲方直接 commit 到 develop（eb6f81a，一次性例外）；之後新增選填設定一律寫成註解
- 日期：2026-10-20

### D-011 agent 的 `docker compose *` 權限可繞過「不可讀 .env」
- 決定：B. 維持放行 `docker compose *`，接受風險（資安 v0.6.0 M-3）
- 理由：甲方優先讓本機測試順暢；`.env` 只在本機，agent 規則仍禁止讀取
- 日期：2026-10-20

### D-008 `task.py new` 在 sandbox 裡無法開單
- 決定：B. 修上游範本：甲方在 sandbox 外跑 `check_env.py` 時寫「設定齊全」戳記（`.env.example` 雜湊，不含值），`task.py` 讀不到 `.env` 時改查戳記；修好前用 A（甲方以 `!` 代開單）。同一次範本修正一併處理 D-012 與 worktree 內 pytest 碰 `.env` 失敗、`pr.py merge` 在 sandbox 刪不掉 worktree 的 `.env` 連結而留下資料夾（甲方手動 `rm -rf .worktrees/<id>`）
- 日期：2026-10-20

### D-010 bot 允許清單沒設時要不要改成拒絕（fail closed）
- 決定：A. `TELEGRAM_ALLOWED_CHAT_IDS` 沒設就啟動失敗；要開放所有人必須明確設 `TELEGRAM_ALLOW_ALL=true`
- 理由：權限預設值應 fail closed，避免上雲或重建 `.env` 時漏設而默默對外開放（資安 v0.6.0 M-1）
- 影響：設計文件 9.2、開發規格 7.21、`.env.example`；不擋 v0.6.0，排進 v0.7.0（派工單 `bot-allowlist-required`）
- 日期：2026-10-20

### D-012 worktree 的 `.venv` 連結被當成未提交修改，`pr.py open` 拒絕
- 決定：A. 甲方在本機 `.git/info/exclude` 加 `.venv`（已執行）；上游範本 GITIGNORE 改成不加斜線，併入 D-008 的範本修正
- 日期：2026-10-20

### D-013 `task.py new` 建 worktree 時寫不進 `.claude/agents/`、`.mcp.json`、`.vscode/`，開單失敗
- 決定：A. 修上游範本：worktree 用 sparse-checkout 排除 `.claude/`、`.mcp.json`、`.vscode/`（甲方已更新範本）
- 理由：B 會讓 agent 能改 worktree 裡的 agent 設定，削弱保護
- 日期：2026-10-20

### D-014 階段 7 Dashboard 的呈現方式
- 決定：A. 階段 7 全用 Grafana（同時核可 `grafana/grafana-oss` image 與 `grafana-clickhouse-datasource` plugin）；自建 web 前端延到階段 9 一起做
- 理由：B 的好處與之後的前端需求重疊，等階段 9 有 HTTPS 再一起做
- 影響：開發規格 7.25、階段 9 範圍
- 日期：2026-10-20

### D-015 CI 加速要不要加新套件或付費 runner
- 決定：B. 加 pytest-xdist（dev 相依）；不用付費 runner
- 理由：甲方不要額外付費；免費的平行化可以加
- 影響：開發規格 7.26（做法第 15 項）、`test-infra-fast-waits`
- 日期：2026-10-20

### D-016 qa 跑不了 docker compose，整合測試無法獨立驗證
- 決定：A. qa 也可以跑 `docker compose *`（甲方已處理權限）
- 理由：qa 要能獨立驗證 CI 驗不到的項目（離線啟動、開發環境不受影響）
- 日期：2026-10-20

### D-017 Dashboard 變數注入（L-5 #120）怎麼防、怎麼驗收
- 決定：1. 使用者給的字串不進 SQL 結構：`$board`、`$min_score` 一律 percentencode、由 ClickHouse 解碼；驗收只用靜態檢查加正常值檢查，不寫攻擊字串（測試與實測皆同）
- 理由：寫攻擊字串測試的方向被安全機制擋下；改成從格式上保證不可能注入
- 影響：開發規格 7.25、`dashboard-min-score-select` 驗收條件 2
- 日期：2026-10-21

### D-018 封存派工單反覆觸發 gitleaks 誤判
- 決定：根治：gitleaks 不掃 `tasks/` 底下的封存（派工單、qa／review 報告），改 gitleaks 設定而非逐筆加忽略
- 理由：v0.6.0、v0.7.0、backlog 清理三次封存都觸發誤判，且每次修正單的報告又成為下一次的誤判來源
- 影響：gitleaks 設定（派工單 `gitleaks-archive-allowlist`，PR #153）；`tasks/` 只放派工流程文件，不可放設定值或密鑰；v0.8.0 security 審查要更新「`.gitleaks.toml` 存在、排除 `^tasks/`」並抽查 `tasks/` 新增內容；開發規格第 38 行忽略檔說明待下一張改開發規格的單補一句
- 日期：2026-10-21

### D-019 階段 8 BERT fine-tune 的分工
- 決定：A. agent 準備 fine-tune notebook、模型匯出與評估流程；甲方在 Colab／Kaggle 執行訓練並交回模型檔
- 理由：agent 無法操作 Colab／Kaggle
- 影響：開發規格階段 8 S8-01、`bert-design`
- 日期：2026-10-21

### D-020 推論服務的新套件
- 決定：A. 執行期 `onnxruntime`＋`tokenizers`，開發用 `onnx`（不用 torch＋transformers 推論）
- 理由：image 小、載入時不執行模型附帶程式；onnxruntime 有 Python 3.12 x86_64／aarch64 wheel
- 影響：開發規格 7.27、`bert-skeleton`
- 日期：2026-10-21

### D-021 預訓練模型
- 決定：D. ckiplab/bert-base-chinese（GPL-3.0）與 hfl/chinese-macbert-base（Apache-2.0）各訓一版，用人工測試集決定
- 理由：甲方接受 GPL 風險；模型只在自己的機器與 VM 使用、不對外散布。日後若要對外提供或散布模型、產品，須重新評估 GPL
- 影響：開發規格 7.27、`bert-notebook`、`bert-eval-report`
- 日期：2026-10-21

### D-022 notebook 端套件（只裝在 Colab，不進 `uv.lock`）
- 決定：A. `torch`、`transformers`、`optimum[onnxruntime]`
- 影響：`bert-notebook`
- 日期：2026-10-21

### D-023 shadow 推論的資源上限
- 決定：A. 2 CPU、1.5g 記憶體、`INFERENCE_THREADS=2`
- 影響：開發規格 7.27、`bert-shadow-inference`
- 日期：2026-10-21

### D-024 訓練資料（PTT 內文）上傳平台
- 決定：A. Colab，工作階段上傳、不放 Drive
- 理由：Kaggle 條款只取得摘要（非商用）、預設可見度查不到；甲方知悉兩平台條款皆未明文規範論壇內容
- 影響：`bert-notebook`
- 日期：2026-10-21

### D-025 預訓練模型只有 pickle 權重（`pytorch_model.bin`），notebook 怎麼載入
- 決定：B. ckiplab/bert-base-chinese 釘 SFconvertbot 的 safetensors 轉換 PR（`refs/pr/1`，commit `d3e55b839fccbf1bba9e194b8626b18b30fcc5f3`）只載 safetensors；hfl/chinese-macbert-base 沒有 safetensors，在 Colab 載 `.bin`，notebook 第一格要求 `torch>=2.6`（weights_only 預設）、釘 revision、`trust_remote_code=False`
- 理由：有 safetensors 就用；pickle 只在用完即丟的 Colab VM 解開，本機與 VM 仍只載 ONNX／JSON
- 影響：開發規格 7.27「威脅與對策」預訓練模型來源列、7.27 派工順序第 2 步；`bert-notebook`
- 日期：2026-10-22

### D-026 gitleaks 把 Hugging Face 的模型版本號（40 位 hex）誤判成密鑰，所有分支的 CI 都卡住
- 決定：A. `.gitleaks.toml` 只對 `generic-api-key` 加一條放行規則：變數名含 rev／revision／commit／sha **且**值是 40 位小寫 hex 才放行；不逐筆加 `.gitleaksignore`
- 理由：依類別根治、範圍窄，延續 D-018；之後新的 revision 不會再擋 CI
- 影響：`.gitleaks.toml`；chore 單 `gitleaks-revision-allowlist`（調查見 reports/bert-shadow-inference.gitleaks.md）；合併後 PR #165、#166、#167 sync
- 日期：2026-10-25

### D-027 v0.8.0 要不要等甲方訓練模型、shadow 跑滿 3 天才發版
- 決定：A. 現在發版；甲方只驗 README 與流程能看懂，模型相關驗收（docs/uat/v0.8.0.md S15–S18、甲方驗收清單第 2～7 項）改由 #178 追蹤，跑完補 `docs/reports/model-evaluation.md`
- 理由：程式、uat、資安都已驗完；模型好壞是資料結果，不影響這版程式能不能發（比照 D-003）
- 影響：v0.8.0 甲方驗收範圍；#178
- 日期：2026-10-26

### D-028 推文立場分類（設計 14.4）要不要做、排在哪
- 決定：B. 先不做，列 backlog #181，之後再設計；原提問的 D-029（標註 LLM）、D-030（送外部的資料範圍）一併延到設計時再問，選項與調查記在 #181
- 理由：甲方決定；甲方傾向推文短、量少，標註可直接交給 Claude 一次標完，不走文章那套 batch（設計時納入）
- 影響：設計 14.4 維持延伸功能；#181；docs/research/comment-stance.md
- 日期：2026-10-27
