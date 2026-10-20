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

### D-008 `task.py new` 在 sandbox 裡無法開單
- 背景：`task.py new` 會呼叫 `check_env.missing_settings()` 檢查 `.env`，但 sandbox 禁止讀 `**/.env`（連 `exists()` 都不行），直接 `PermissionError` 當掉；`check_env.py` 本身也一樣。所有派工單都卡住（含 `spec-release-order`、階段 7）。流程腳本是甲方的檔案，manager 不能改
- 選項：A. 暫時由甲方在自己的終端機開單：`! python3 scripts/task.py new <id> < <派工單檔>`（我先把派工單寫好，每張單都要甲方跑一次）／B. 修範本（agent-engineering 上游）：`check_env.py` 由甲方在 sandbox 外跑一次後寫一個「設定齊全」的戳記（例：`.env.example` 雜湊），`task.py` 讀不到 `.env` 時改查戳記，修好後 `update.sh` 同步／C. sandbox 開放讀 `.env`（違反「不可讀 .env」，不建議）
- 建議：B 為長期解，修好前先用 A
- 提出：manager（spec-release-order）

### D-010 bot 允許清單沒設時要不要改成拒絕（fail closed）
- 背景：資安 M-1。`TELEGRAM_ALLOWED_CHAT_IDS` 留空＝任何人都能用 bot（訂閱、收警示、觸發 ClickHouse 查詢），與設計文件 9.2「只回應允許清單內的 chat」不一致。看不到別人的資料，但可被濫用與觸發 H-1。你的 `.env` 已填，現況不受影響
- 選項：A. 沒設就啟動失敗；要開放所有人必須明確設 `TELEGRAM_ALLOW_ALL=true`／B. 維持留空不限制，只在文件寫清楚（README 已補）
- 建議：A，權限預設值應該 fail closed；不擋 v0.6.0，排進下一版
- 提出：security（v0.6.0 審查 M-1）

### D-012 worktree 的 `.venv` 連結被當成未提交修改，`pr.py open` 拒絕
- 背景：`task.py new` 會在 worktree 建 `.venv` 符號連結（共用主目錄環境），但 `.gitignore` 寫的是 `.venv/`（只比對目錄），符號連結不會被忽略 → `git status` 出現 `?? .venv` → 每張單的 `pr.py open` 都會拒絕。範本 `init_project.py` 的 GITIGNORE 也是 `.venv/`，是上游問題
- 選項：A. 甲方在主目錄執行 `echo .venv >> .git/info/exclude`（只影響本機、所有 worktree 立即生效，不必 sync）／B. 甲方把 `.gitignore` 的 `.venv/` 改成 `.venv` 直接 commit 到 develop（既有兩張單要 sync 才拿得到）
- 建議：A 立即解卡，另外在上游範本把 GITIGNORE 改成 `.venv`、`node_modules`（不加斜線），之後 update.sh 同步
- 提出：manager（spec-release-order）

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
