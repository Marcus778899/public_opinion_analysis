# 派工單 test-infra-design

- **類型**：docs
- **負責**：architect
- **目標**：設計 compose `test` 服務（讓整合測試在 sandbox 外的容器裡跑）與 CI 整合測試加速（#78）
- **背景**：agent 的 Bash 在 sandbox 內，testcontainers 連不到 docker socket，整合測試只能靠 CI；唯一放行的是直接下 `docker compose …`（D-011）。CI Integration Test 約 7 分鐘（Check 40 秒）：testcontainers 開 8 個容器且多為 module 級、每次重拉映像、序列執行、docs-only push 也跑全套。方向見 #78：先量 `--durations`、session 共用、docs-only 跳過、快取映像；pytest-xdist 等新相依屬決策②要開待決定
- **設計依據**：#78；`docs/development-spec.md`（測試章節、2.x 指令）；`.github/workflows/ci.yml`；`infra/docker-compose*.yaml`；`Makefile`；`tests/integration/`
- **相依**：無
- **負責檔案**：
  - `docs/development-spec.md`
  - `docs/realtime-sentiment-radar-design.md`
- **禁區**：不改程式、CI、compose、Makefile（實作由後續派工單做）；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 開發規格寫明 compose `test` 服務的用法（agent 怎麼下指令跑整合測試、與開發／e2e 容器的關係，#41）與 CI 加速方案（附實測的 `--durations` 或步驟耗時作依據）
  - [ ] 列出實作派工順序（task_id、負責、負責檔案、驗收測試目錄）
  - [ ] 「需調查」「待決定」「自行決定」分開列在回報；新相依、CI 付費選項列待決定
- **驗證指令**：`git diff --stat develop`
- **回報檔**：`reports/test-infra-design.json`

## 執行資訊（task.py 產生）

- Issue：#84
- 分支：`docs/test-infra-design`（從 develop 開出）
- 工作目錄：`.worktrees/test-infra-design`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
