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

### D-009 `.env.example` 把選填設定當成必填，`task.py new` 拒絕開單
- 背景：`check_env` 把 `.env.example` 每個沒註解的 `KEY=` 都當必填，空值就擋。`OPENROUTER_API_KEY`（只有選 openrouter 當標註者才用）、`API_CORS_ORIGINS`（留空＝不開放跨網域，是正確的預設）在程式裡都是選填，卻擋住開單。改 `.env.example` 要走派工單，但開不了單，形成死結
- 選項：A. 甲方直接改 `.env.example`，把這兩行改成註解（`# OPENROUTER_API_KEY=`、`# API_CORS_ORIGINS=`，說明保留），自己 commit、push 到 develop（一次性的開機例外）／B. 甲方在 `.env` 填值：OpenRouter 填真的 key；CORS 沒有「不開放」的值可填，只能填一個來源（例 `http://localhost:3000`），等於放寬跨網域，不建議
- 建議：A；程式行為不變，之後新增選填設定一律寫成註解
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
