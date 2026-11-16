# 派工單 bbs-retest-design

- **類型**：docs
- **負責**：architect
- **目標**：設計 v0.9.0 的 BBS 補實驗（D-048）：混合方案 1 條連線輪流讀 4 篇的實測延遲、同帳號同時連線數實測（D-049），以及實驗工具要先修的項目與派工順序
- **背景**：
  - 第一次實驗結果見 `docs/reports/bbs-spike.md`：P2 p50(E) 45 秒但扣掉不符選取規則的第 1 篇只剩 35 則（部分證實）；`N_max`=4、需 9 條、只證實 1 條
  - 甲方決定：只要最熱的前幾篇 1 分鐘內；晚間 20:00～23:00；4 篇都符合選取規則、可跨看板；P2 樣本 ≥ 100 則且 ≥ 3 篇；補實驗另給 3 次登入（每條連線算一次）、間隔 ≥ 10 分鐘、沿用小號；連線數實測不踢線、出現警告即停（D-049）
  - 工具必修：資安 O-2（輸出掃描可能刪 ledger）、UAT F-1（門檻判定未排除不符選取規則的文章）；順手：#327、#328、資安 O-1（SILENT 根因與 7.31 威脅表說法）、#329（PTT_BBS_* 進所有容器，提出處理方式；改回選填屬推翻 D-046，列待決定）
  - 新 ledger 與輸出位置要與第一次實驗分開，第一次的資料保留
- **設計依據**：`docs/development-spec.md` 7.31；`docs/reports/bbs-spike.md`；`docs/security/v0.9.0.md`；`docs/uat/v0.9.0.md`；D-043、D-045～D-049
- **相依**：無
- **負責檔案**：
  - `docs/development-spec.md`
- **禁區**：不改 `src/`、`tools/`、`infra/`、`tests/`；不連真實 PTT；不讀 `.env`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 7.31 新增補實驗一節：步驟、上限（含多連線）、立即停止、量測與門檻、混合方案判定、樣本下限
  - [ ] 列出派工順序（task_id、負責、負責檔案、驗收測試目錄）、需調查、待決定
  - [ ] O-1 的威脅表說法修正
- **驗證指令**：`git diff --stat origin/develop...HEAD`；`make check`
- **回報檔**：`.agent/reports/bbs-retest-design.json`

## 執行資訊（ae task 產生）

- Issue：#330
- 分支：`docs/bbs-retest-design`（從 develop 開出）
- 工作目錄：`.worktrees/bbs-retest-design`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`

## 追加 2026-11-09

- **需調查結果（G-9-1）**：`docs/research/bbs-multi-login.md`。pttbbs 沒有數字上限；重複登入時顯示「您想刪除其他重複登入的連線嗎？[Y/n]」（預設 Y＝踢掉舊連線）；researcher 在 PyPtt 2.3.16 沒找到對應處理，但 PyPtt 有 `kick_other_session` 參數，兩者矛盾要你讀本機 .venv 核對。依結果修訂 7.31 G 的 M 階段：確認 B、C 登入時一定回答「不刪除」、不會因預設值踢掉 A，並把這些畫面文字加進立即停止關鍵字；做不到就寫明 M 階段的風險與替代做法
