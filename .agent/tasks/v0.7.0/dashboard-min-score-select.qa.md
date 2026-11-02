PASS 2698314

# QA：dashboard-min-score-select（commit 2698314，驗收測試鎖定 c15d493）

結論：PASS，0 個問題。上一輪（0848c15）唯一的問題（開發規格 7.25 兩處舊說法）已修好；0848c15 到 2698314 只改文件，不需重做 Grafana 實測。依 D-017 本輪沒有使用攻擊字串。

## 驗收條件逐條

| # | 條件 | 結果 |
|---|---|---|
| 1 | min_score 下拉（0.4～0.7、預設 0.5）有說明 | 通過。radar.json 實際讀出：type=custom、query=`0.4,0.5,0.6,0.7`、current=0.5、multi/includeAll=false、description 有寫（低於此值標為「不確定」、數字越大越嚴格）；acceptance 測試也通過 |
| 2（依 D-017 改寫） | 所有 board／min_score 引用一律 percentencode、放 SQL 單引號內 | 通過。radar.json 的引用共 16 處，`grep -o` 統計：`${board:percentencode}` 11 次、`${min_score:percentencode}` 5 次，沒有其他格式的引用；靜態測試包含在下面 179 個測試內 |
| 3 | 驗收測試全過、單元、ruff | 通過（見下） |
| 4 | 開發規格 7.25 同步 | 通過（見下） |
| 5 | PR CI 全綠 | 本輪未驗（派工未要求；上一輪查過的 CI 狀態對應舊 commit，不採用） |

## 自己執行的指令與輸出

1. 驗收測試未被改：`git diff c15d493 HEAD --stat -- tests` 無輸出（c15d493 之後 tests 目錄零差異）；`git status --short` 乾淨。

2. `docker compose --env-file .env -f .worktrees/dashboard-min-score-select/compose.yaml run --rm test pytest tests/integration/acceptance/dashboard tests/integration/dashboard -q`
   → `179 passed in 19.05s`

3. `uv run pytest tests/unit -q`（worktree）→ `1114 passed in 4.88s`
   `uv run ruff check .` → `All checks passed!`
   `uv run ruff format --check .` → `252 files already formatted`

4. 開發規格 7.25 檢查（`grep -n "威脅表：，\|丟棄\|'a','b'\|sqlstring\|singlequote\|allowCustomValue" docs/development-spec.md`）：
   - 舊說法已消失：「威脅表：，」「丟棄」「'a','b'」都沒有命中（第 900 行的「丟棄」是不相干的 watermark 說明）。
   - 第 1035 行：改為 `allowCustomValue: false` 只是 UI 層限制、Grafana 13.0.2 首次載入時網址值不會被丟棄、不是安全防線。與 radar.json（兩個變數 allowCustomValue 皆 false）一致，並如實說明不是防線。
   - 第 1048 行：寫 `${board:percentencode}`、`${min_score:percentencode}` 放單引號內、ClickHouse `decodeURLComponent` 解碼、多選 `{a,b}` 整串編碼後 `trim(BOTH '{}' …)` 再切、`toFloat64OrDefault(…, 0.5)`；半截句已改為「威脅表見下」；空選取 `%7B%7D`。「sqlstring」只出現在「不用 sqlstring」的原因說明，與實作一致。
   - 威脅表（第 1052 行起）：兩列，對策為全部引用 percentencode、解碼在 ClickHouse 內、靜態測試要求每個引用都是此格式；非數字退回 0.5、看板比對不到回空，與 SQL 一致。
   - 面板描述（min_score 選項、預設 0.5、說明文字）與 radar.json 一致。沒有發現其他與實作矛盾處。

5. 0848c15 到 2698314：`git diff 0848c15 2698314 --stat` 只有 `docs/development-spec.md | 4 ++--`；`infra`、`src` 無差異，radar.json 與上一輪驗過的完全相同。因此上一輪的 Grafana 實測（bundle 原始碼的 percentencode 展開、/api/ds/query 對底線、中文、連字號、多選、All、空選取、min_score 四個選項的結果）仍然有效，沿用該結果，本輪未重做；本輪重新做的是上面的指令與文件逐項對照。

6. 寫死的設定值：本輪差異只有文件，沒有新增 port、網址、token。

## 限制（延續上一輪）

沒有真瀏覽器畫面（Chrome 在 sandbox 無法啟動），前端展開靠 Grafana bundle 原始碼與 /api/ds/query 實測佐證。後續補強已開 backlog #125，不在本單範圍。

收尾：已執行 `docker compose --env-file .env -f .worktrees/dashboard-min-score-select/compose.yaml down -v`，容器、網路、volume 都已移除。
