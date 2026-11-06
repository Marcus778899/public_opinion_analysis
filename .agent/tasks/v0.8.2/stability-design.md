# 派工單 stability-design

- **類型**：docs
- **負責**：architect
- **目標**：v0.8.2 穩定性小版（D-042）的設計、契約與實作派工順序
- **背景**：
  - 範圍與甲方決定見 D-041、D-042；問題細節與證據見各 issue 與 `.agent/reports/dev-stall-recover.json`、`.agent/reports/inference-ckip-up.json`、`docs/uat/v0.8.1.md`、`docs/security/v0.8.1.md`
  - #281 甲方決定：JsonProducer 進入 fatal（`_FATAL`）就 `log.critical` 並非 0 結束，交給 docker restart 恢復（所有用它的服務），不做程式內重建；另確認 #224 有沒有涵蓋「scheduler 沒送出 crawl.tasks」
  - #282 甲方決定（D-041）：Connect 內部 topic 改 **2 份副本**，用 partition reassignment、不刪資料不重建 connector、先備份 connector 設定；connect 健康檢查改確認 connector 存在；cdc-watchdog 在 REST 正常但 404 持續時記 ERROR；connect_status topic 不存在原因待查
  - #289 甲方決定：正式 inference 比照 D-023 設 2 CPU、2g、`INFERENCE_THREADS=2`；另確認只對 op=c 推論是否為預期。#262：init 遇 Debezium task FAILED 先重啟 task 再判斷。#268：PTT 標頭未來時間不可讓補抓終點 since 跑到未來
  - 小項：#276（v1 殘留文字）、#263（import_model 錯誤訊息中文一行帶下一步、derive_model --help）、#270（`--sha256` 必填）、#277（CI 先 checkout 工具；可清 `.gitleaks.toml` 無作用的 `^tasks/`）、#269（說明既有 grafana_data 換 admin 密碼）、#271 剩下兩項（回放同分鐘重複 alert_id、殘留警告英文）
- **設計依據**：`docs/development-spec.md`（7.16、7.20、7.22、7.28、第 6 章 inference 與 shadow）；D-023、D-034、D-039、D-040、D-041、D-042；CLAUDE.md「資料與架構約定」
- **相依**：無
- **負責檔案**：
  - `docs/development-spec.md`
  - `docs/realtime-sentiment-radar-design.md`（行為有變時同步）
  - `docs/domain/`（有新的業務規則或術語時）
- **禁區**：不寫實作程式；不動開發環境的 Kafka、容器與資料；新增套件、付費服務屬決策分級，列「待決定」
- **驗收測試**：無
- **驗收條件**：
  - [ ] 每個問題（#281、#282、#289、#262、#268、小項）的修法、行為變更與錯誤處理寫進開發規格
  - [ ] #282：副本數變更的操作步驟（備份、reassignment、驗證、回復方式）與 compose／建 topic 設定的對應改法
  - [ ] 每張實作單的驗收測試目錄與「受影響的既有驗收測試」
  - [ ] 實作派工順序（task_id、負責、通道 full／fast、可否平行、負責檔案、驗收測試目錄）；「需調查」「待決定」「自行決定」三張表
- **驗證指令**：無（文件）
- **回報檔**：`.agent/reports/stability-design.json`

## 執行資訊（ae task 產生）

- Issue：#291
- 分支：`docs/stability-design`（從 develop 開出）
- 工作目錄：`.worktrees/stability-design`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
