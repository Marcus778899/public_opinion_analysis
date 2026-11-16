# 派工單 bbs-retest-tool

- **類型**：feat
- **負責**：backend
- **目標**：在 `tools/bbs_spike.py` 加補實驗子命令 `retest`、`summarize-retest`（延遲 R2 階段＋同帳號多連線 M 階段），並修 G-4 列的工具問題，讓甲方晚間手動跑補實驗
- **背景**：
  - 補實驗（D-048）：晚間 20:00～23:00、4 篇都符合選取規則，1 條連線輪流讀 4 篇量延遲；之後實測同帳號同時連線數（D-049：不踢線、出現警告或被踢即停，每條連線算一次登入，計入 3 次額度）
  - D-051：延遲階段跑滿 60 分鐘樣本仍不足時，不開 B、C，保留登入額度給一次重跑延遲
  - D-050：補實驗報告合併後帳密變數改回選填（不是這張單的工作）；compose 隔離單 `bbs-env-isolation` 不做
  - PyPtt 仍釘 2.3.16、只在 `bbs-spike` group（D-043）；agent 與測試都不可連真實 PTT（ptt.cc、term.ptt.cc）、不可讀 `.env`；帳密只從 `PTT_BBS_USERNAME`、`PTT_BBS_PASSWORD` 讀
  - 第一次實驗的資料 `data/spike/bbs/` 不可被覆寫或刪除（`--out` 指到它要拒絕，見 G-2）
- **設計依據**：`docs/development-spec.md` 7.31 G（G-1～G-6、G-8；其餘照 7.31 B、C、F）；`docs/research/bbs-multi-login.md`（PyPtt 多重登入處理以 7.31 G-3a 為準，研究檔對 PyPtt 的說法有誤）；D-043、D-048、D-049、D-050、D-051
- **相依**：無（bbs-retest-design 已合併）
- **負責檔案**：
  - `tools/bbs_spike.py`
  - `tests/unit/tools/test_bbs_spike.py`
- **禁區**：不改 `src/`、`infra/`、CI、`pyproject.toml`、`uv.lock`；不連真實 PTT；不讀 `.env`；fixture 手寫，不放真實推文或使用者 ID；不改既有函式簽名（G-4）
- **驗收測試**：
  - `tests/unit/acceptance/bbs-retest-tool/`
- **驗收條件**：
  - [ ] G-2 登入前檢查各項拒絕時不登入、不寫 ledger；ledger 在 `data/spike/bbs-retest/`、記 `conn`，3 次與 10 分鐘間隔跨連線計算
  - [ ] R2 的 40／60 分鐘與提前結束、樣本不足時不開 B、C（D-051）
  - [ ] M 階段開線時間、B／C 讀取間隔、證實條件、各種停止與 k 的計算
  - [ ] G-3a：多重登入關鍵字只查已開著的連線；開線後舊連線讀取失敗即停；登入失敗的連線不登出、不送鍵
  - [ ] G-4 每一項修正（含資安 O-1、O-2，UAT F-1、F-2，#327、#328）都有測試，第一次實驗的驗收測試 `tests/unit/acceptance/bbs-spike-tool/` 照常通過
  - [ ] G-5 判定與 summary 欄位；summary 不含使用者 ID、推文內容與帳密
  - [ ] 沒裝 `bbs-spike` group 時 `uv run pytest tests/unit` 仍能跑
  - [ ] 行為與 7.31 G 有出入要回報，不自行改文件
- **驗證指令**：`make check`；`uv run pytest tests/unit/acceptance/bbs-retest-tool tests/unit/acceptance/bbs-spike-tool tests/unit/tools/test_bbs_spike.py -q`
- **回報檔**：`.agent/reports/bbs-retest-tool.json`

## 執行資訊（ae task 產生）

- Issue：#332
- 分支：`feat/bbs-retest-tool`（從 develop 開出）
- 工作目錄：`.worktrees/bbs-retest-tool`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
