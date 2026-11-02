# 派工單 dashboard-var-test-hardening

- **類型**：test
- **負責**：backend
- **通道**：fast
- **目標**：補強 Dashboard 變數的測試，讓「變數一律 percentencode 且在單引號內」真的被檢查到
- **背景**：dashboard-min-score-select 仲裁的補強建議（tasks/v0.7.0/dashboard-min-score-select.ruling.md、#125）：①兩個 `test_every_board_and_min_score_reference_uses_percentencode` 沒斷言 `r.in_string`，開發規格 7.25 威脅表要寫成「此格式且在單引號內」；②`test_variable_formats.py` 的 docstring 仍是 sqlstring 時代的說法；③P_VOLUME 時序寬表的看板名稱在欄位 labels，`other.board not in text` 等於沒檢查。決策見 D-017
- **設計依據**：`docs/development-spec.md` 7.25（威脅表）；D-017
- **相依**：無
- **負責檔案**：
  - `tests/integration/dashboard/test_variable_formats.py`
  - `tests/integration/acceptance/dashboard/test_panels.py`
  - `tests/integration/dashboard/_dash.py`
  - `docs/development-spec.md`
- **禁區**：不改 `infra/grafana/` 的 dashboard 與 provisioning、不改 `src/`；不寫攻擊字串測試（D-017）；不放寬既有斷言；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 兩個 percentencode 測試都斷言每個 `$board`、`$min_score` 引用 `in_string` 為真；目前 dashboard 通過
  - [ ] P_VOLUME 的檢查改成看欄位 labels（或等效），能抓到別的看板混入；回報說明怎麼確認它不是空轉
  - [ ] docstring 與開發規格 7.25 威脅表改成「percentencode 且在單引號內」
  - [ ] `docker compose --env-file .env -f .worktrees/dashboard-var-test-hardening/compose.yaml run --rm test` 全過（跑前 `docker compose ls` 確認沒有其他測試堆疊），做完 `down -v`
  - [ ] `make check` 通過；PR 的 CI 全綠
- **驗證指令**：`make check`；上面的 compose 指令
- **回報檔**：`reports/dashboard-var-test-hardening.json`

## 執行資訊（task.py 產生）

- Issue：#142
- 分支：`test/dashboard-var-test-hardening`（從 develop 開出）
- 工作目錄：`.worktrees/dashboard-var-test-hardening`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-21

### reports/dashboard-var-test-hardening.qa.md

FAIL 37354bd

# 驗證證據 dashboard-var-test-hardening

## 實際執行
- `make check`：1134 passed（worktree 內）
- `docker compose ls`：無其他堆疊；`docker compose --env-file .env -f .worktrees/dashboard-var-test-hardening/compose.yaml run --rm test`：`329 passed in 43.08s`；已 `down -v`（容器、volume、network 全移除）
- `grep -rn "TODO(dashboard-var" src tests`：無結果
- `gh pr checks 143`：Check pass、Security pass、Integration Test pending（驗證當下 CI 尚未全綠）

## 逐條
1. 兩個 percentencode 測試加了 `in_string` 斷言：通過。我用 `$TMPDIR` 一次性腳本直接呼叫 `references()`：
   - `a = ${board:percentencode}` -> in_string False（會被新斷言抓到）
   - `x = 'a' || ${board:percentencode}` -> False
   - `a IN ('${board:percentencode}')` -> True
   所以「不在引號內就失敗」成立。
2. P_VOLUME：`panel_text` 把每個 frame 的欄名、labels（JSON）、所有值串成文字，`other.board not in text` 現在確實涵蓋 labels；加上 `mine.board in text` 的正向斷言證明 labels 有被讀到（329 通過即實證）。我獨立推演：文字包含全部 labels，別的看板混入必然出現在 text，非空轉。沒有做刻意混入的反向實驗，但推演成立，我接受，不列為問題。
3. docstring 與 7.25 已改成「percentencode 且在單引號內」——但與實作不一致，見問題 1。
4. compose 測試：通過。
5. `make check` 通過；PR CI：Integration Test 仍 pending，尚未確認全綠（問題 2）。

## 問題（共 2 個）
1. 文件與實作不一致：docstring 與開發規格 7.25 寫「在單引號內」，但 `_dash.references()` 的 `in_string` 把單引號、雙引號、反引號都視為「引號內」。重現：
   `PYTHONPATH=. uv run python -c "from tests.integration.dashboard._dash import references; print([(r.fmt,r.in_string) for r in references('a = \"\${board:percentencode}\"')])"`
   結果 `[('percentencode', True)]`；反引號同樣 True。ClickHouse 中雙引號與反引號是識別字，不是字串值，新斷言放過這種寫法，威脅表聲稱的「單引號內」沒被真正檢查。修法擇一：新斷言改成只認單引號（references 回報引號種類，或另加 quote_char 欄位）；或把文件改成「在 SQL 引號內」。_dash.py 在負責檔案內，改測試輔助即可。補一個 helper 層的反向測試（雙引號、反引號、引號外各一例）。
2. 驗收條件「PR 的 CI 全綠」於驗證時 Integration Test 仍 pending，無法確認；請 manager 在修正後待 CI 完成再確認。

- 問題 2（CI pending）不用處理，push 後由 manager 確認 CI。只修問題 1：in_string 只認單引號，並補單元或整合測試證明雙引號、反引號內的引用 in_string 為 False。
