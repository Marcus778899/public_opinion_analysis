# 派工單 bbs-spike-design

- **類型**：docs
- **負責**：architect
- **目標**：設計 v0.9.0 的 PTT BBS spike（#57）：要查的問題、一次性延遲實驗的做法與派工順序。要查：站規與停權風險；同帳號同時登入數與 3 個爬蟲的分工；實際延遲並與網頁版比較；相依套件（PyPtt 或自行解析終端機畫面）；推文樓層、分鐘級時間、刪文、箭頭與 `raw.posts` 的對應
- **背景**：
  - 網頁版文章頁約 10 分鐘才更新（7.22），瓶頸在資料來源。甲方結論：這版只做 spike 不導入；導入與否看報告後由甲方決定，導入另開下一版
  - 導入門檻：熱門文章新推文從出現到被讀到 p50 在 1 分鐘內，只需涵蓋熱門文章；達不到就不導入
  - 帳號：甲方已註冊專用小號，帳密由甲方寫進 `.env`；請訂變數名稱加到 `.env.example`（選填，寫成註解，D-009）；agent 不可讀 `.env`；log 與結果不可含帳密
  - 實驗連真實 PTT：一次性、低頻率、由甲方在自己的終端機手動執行，不進測試流程；自動化測試仍不可連真實 PTT；依站規定保守的登入頻率與連線數上限，站規不明時選最保守的做法
  - 新增相依（含實驗用套件）屬決策分級②，列待決定；外部資料列「需調查」，由 researcher 查後交回你修訂
- **設計依據**：#57；`docs/development-spec.md` 7.22、「後續階段」13；`docs/realtime-sentiment-radar-design.md` 4.2
- **相依**：無
- **負責檔案**：
  - `docs/development-spec.md`
  - `.env.example`
- **禁區**：不改 `src/`、`tools/`、`infra/`；不連真實 PTT；不讀 `.env`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 開發規格新增 spike 一節：要回答的問題、實驗步驟與頻率上限、量測方法（p50、與網頁版比較的基準）、報告位置與格式
  - [ ] 列出派工順序（task_id、負責角色、負責檔案）、需調查、待決定
  - [ ] `.env.example` 有帳密變數名稱，不含值
- **驗證指令**：`git diff --stat origin/develop...HEAD`；`make check`
- **回報檔**：`.agent/reports/bbs-spike-design.json`

## 執行資訊（ae task 產生）

- Issue：#317
- 分支：`docs/bbs-spike-design`（從 develop 開出）
- 工作目錄：`.worktrees/bbs-spike-design`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
