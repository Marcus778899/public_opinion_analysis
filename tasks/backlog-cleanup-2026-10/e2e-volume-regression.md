# 派工單 e2e-volume-regression

- **類型**：test
- **負責**：backend
- **通道**：fast
- **目標**：加一條通用回歸測試：e2e 合併後任何服務都不掛開發環境的 volume；開發規格補上遺漏的說明
- **背景**：e2e-grafana-volume（PR #114）review 建議（#118）：compose v2 的 `down -v` 只刪啟用中服務引用的 volume，所以「合併後沒有服務掛開發 volume」是 e2e 不刪開發資料的安全前提；目前只有 grafana、app_logs 個別檢查。另 bot-skip-alert-log（PR #133）review 建議開發規格「推送對象」補一句略過時會記 log
- **設計依據**：`docs/development-spec.md` 第 5 章 e2e（約第 310 行）、約第 994 行「推送對象」；`tests/unit/e2e_support/test_e2e_grafana_volume.py` 的 `merged_mounts` 規則
- **相依**：無
- **負責檔案**：
  - `tests/unit/e2e_support/test_e2e_no_dev_volumes.py`
  - `docs/development-spec.md`
- **禁區**：不改 compose 檔、Makefile、既有的 `tests/unit/e2e_support/` 測試（要共用 `merged_mounts` 就在新檔自己實作或 import，不搬動舊檔）；不改 `src/`、`scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 新測試逐一看開發 compose 的每個服務，斷言 e2e 合併後沒有任何掛載來源是 `infra/docker-compose.yaml` 頂層 volumes 的開發 volume；目前 develop 上通過
  - [ ] 新測試能抓到違規：回報說明怎麼確認（例如以測試內的假 compose 資料重現一個違規案例）
  - [ ] 開發規格第 5 章 e2e volume 清單補上 `e2e_heat_state`；「推送對象」補一句被通知設定或「不再通知」略過時記 INFO log（內容 chat、unit、原因）
  - [ ] `make check` 通過；PR 的 CI 全綠
- **驗證指令**：`make check`
- **回報檔**：`reports/e2e-volume-regression.json`

## 執行資訊（task.py 產生）

- Issue：#139
- 分支：`test/e2e-volume-regression`（從 develop 開出）
- 工作目錄：`.worktrees/e2e-volume-regression`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
