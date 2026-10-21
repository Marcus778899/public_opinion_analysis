# 派工單 dashboard-min-score-select

- **類型**：feat
- **負責**：backend
- **目標**：dashboard 的「情緒信心下限」（min_score）從文字框改成下拉選單並加說明文字；面板 SQL 的變數改用跳脫格式，修資安 L-5
- **背景**：甲方驗收 v0.7.0 時要求（看不出要填 0～1 的數字）。選項由 manager 定：0.4、0.5、0.6、0.7，預設 0.5（與 TELEGRAM_SENTIMENT_MIN_SCORE 預設相同）。說明文字要讓一般使用者看懂：模型三類最高機率低於此值的文章標為「不確定」，影響情緒分布與熱門文章排行。資安 L-5（docs/security/v0.7.0.md、#120）：`'$min_score'` 與 `$board` 直接拼進 SQL，可經網址參數改寫查詢，本單一併改成跳脫格式（例如 sqlstring）
- **設計依據**：`docs/development-spec.md` 7.25（面板、變數、威脅表）；`docs/security/v0.7.0.md` L-5；`docs/uat/v0.7.0.md` 甲方驗收清單
- **相依**：無
- **負責檔案**：
  - `infra/grafana/dashboards/radar.json`
  - `docs/development-spec.md`
- **禁區**：不改面板的查詢邏輯與其他面板；不改 provisioning、compose、`src/`；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：
  - `tests/integration/acceptance/dashboard/test_panels.py`
  - `tests/integration/dashboard/`
- **驗收條件**：
  - [ ] min_score 是下拉選單（0.4、0.5、0.6、0.7，預設 0.5），有說明文字
  - [ ] 經網址參數帶入含單引號或 SQL 片段的 min_score、board 值，不會改變查詢結構（面板報錯或回空皆可，不可執行注入的 SQL）
  - [ ] 驗收測試全過，`make check` 通過；`docker compose --env-file .env -f .worktrees/dashboard-min-score-select/compose.yaml run --rm test` 全過並附輸出；交單前 down -v
  - [ ] 開發規格 7.25 的變數說明與威脅表同步
  - [ ] PR 的 CI 全綠
- **驗證指令**：`make check`；`docker compose --env-file .env -f .worktrees/dashboard-min-score-select/compose.yaml run --rm test`
- **回報檔**：`reports/dashboard-min-score-select.json`

## 執行資訊（task.py 產生）

- Issue：#123
- 分支：`feat/dashboard-min-score-select`（從 develop 開出）
- 工作目錄：`.worktrees/dashboard-min-score-select`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-21

### reports/dashboard-min-score-select.qa.md

FAIL ff499e6

# QA：dashboard-min-score-select（commit ff499e6，驗收測試鎖定 61181af）

結論：FAIL，3 個問題。主因是驗收條件 2「不可執行注入的 SQL」在含反斜線的 board 值上不成立（已在 Grafana 13.0.2 的 /api/ds/query 實測）。

## 驗收條件逐條

| # | 條件 | 結果 |
|---|---|---|
| 1 | min_score 下拉（0.4～0.7、預設 0.5）有說明 | 通過。GET /api/dashboards/uid/radar 讀回：type=custom、query=`0.4,0.5,0.6,0.7`、current=0.5、description 有寫，multi/includeAll 皆 false |
| 2 | URL 帶單引號或 SQL 片段不會改變查詢結構 | 單引號類通過；反斜線類 FAIL（見問題 1、2） |
| 3 | 驗收測試全過、make check、compose test | 通過（輸出如下） |
| 4 | 開發規格 7.25 變數說明與威脅表同步 | 已更新；但威脅表「主要靠 allowCustomValue:false」的主張與 Grafana 13.0.2 行為不符（問題 2） |
| 5 | PR 的 CI 全綠 | 通過。`gh pr checks 124`：Check pass 51s、Integration Test pass 2m15s、Security pass 27s |

## 自己執行的指令與輸出

`pre-commit run --all-files`（在 worktree）：全部 Passed（trailing whitespace、end of files、check yaml、ruff、ruff format、bandit）。
`uv run pytest tests/unit -q`：`1114 passed in 5.19s`。

`docker compose --env-file .env -f .worktrees/dashboard-min-score-select/compose.yaml run --rm test`（預設 -n auto，8 workers）：
`======================== 380 passed in 68.82s (0:01:08) ========================`

同指令加 `pytest tests/integration -n 0 -q`：`380 passed in 160.07s (0:02:40)`

做完已 `down -v`（含我為實測加的 override），容器、網路、volume 都移除。

## 問題

### 問題 1（主要）：含反斜線的 board 值在「各看板推文量」面板執行了注入的 SQL

實測環境：compose 的 grafana 加 override（對外 13000 port、匿名 Admin，只在 QA 暫用，已 down -v），clickhouse 寫入 BoardA（3 則推文）、SecretB（4 則推文，且 posts_latest 沒有 SecretB，所以 board 下拉選單裡不會有它）。
我把 Grafana 13.0.2 前端 sqlstring 的實際程式碼（見問題 2）移植成 Python：`'` 變 `''`、`"` 變 `\"`、反斜線不處理。取 provisioning 的 rawSql，替換 `${board:sqlstring}`，經 `POST /api/ds/query`（真的 plugin、真的 readonly 帳號）送出：

| 面板 | board 值 | 結果 |
|---|---|---|
| 各看板推文量 | `BoardA` | 推文數 3 |
| 各看板推文量 | `SecretB` | 推文數 4 |
| 各看板推文量 | `\') OR 1=1 --` | 兩列：推文數 3 與 4，等於 `OR 1=1` 生效，看到下拉選單以外的看板 |
| 各看板推文量 | `x') OR 1=1 --` | 空（單引號被擋，正常） |
| 其他 4 個含 board 的面板 | `\') OR 1=1 --` | ClickHouse 語法錯誤（巢狀子查詢的括號沒配對），只是 payload 沒針對它們設計，不代表安全 |

重現（任何人可做）：
1. 在 worktree 目錄起 stack（含 grafana），種 comments_latest 兩個看板。
2. 取 `/api/dashboards/uid/radar` 的 panel「各看板推文量」target.rawSql，把 `${board:sqlstring}` 換成 `'\'') OR 1=1 --'`（即 sqlstring 對 `\') OR 1=1 --` 的輸出），送 /api/ds/query。
3. 回傳含全部看板的列。展開後 SQL：`board IN ('\'') OR 1=1 --')`，ClickHouse 把 `\'` 當跳脫引號，字串在第二個 `'` 結束，`--` 把尾端 `')` 註解掉，語法剛好合法。

唯讀帳號限制了破壞力（最壞是讀到 grafana 帳號本來就能讀的資料），但驗收條件明寫「不可執行注入的 SQL」，這裡的 SQL 結構確實被改了。
工人在回報裡已承認 SQL 端擋不住反斜線。

### 問題 2：工人的防線 allowCustomValue:false 在 Grafana 13.0.2 靜態證據顯示擋不住網址參數

沒辦法做真瀏覽器實測：Chrome（/Applications/Google Chrome.app）在 sandbox 裡啟動失敗（crashpad `bootstrap_check_in ... Permission denied`、`Failed to create a ProcessSingleton`），compose 也沒有瀏覽器映像。以下是從執行中的 Grafana 13.0.2 容器取出的前端 bundle（`/public/build/522.e579a60fe94dd7b6ef93.js`、`7457...js`）的靜態分析：

1. sqlstring 格式器：`const E={"'":"''",'"':'\\"'}; function b(S){const _=new RegExp("'|\"","g"); ... "'"+replace(P,_,K=>E[K]??"")+"'"`。只處理 `'` 與 `"`，反斜線不處理（證實工人的說法）。
2. `allowCustomValue` 在 query／custom 變數只被當成 prop 傳給下拉選單元件（`VariableValueSelect`／`MultiSelect` 的 `allowCustomValue:M`，預設 true）。bundle 裡 `getStateUpdateGivenNewOptions`（驗證變數值是否在選項內）完全沒有讀 `allowCustomValue`。
3. 網址路徑：`updateFromUrl` → `if(!this._sceneObject.isActive) this._sceneObject.skipNextValidation=!0` → `changeValueTo(values)` 直接把網址值設成變數狀態；`interceptStateUpdateAfterValidation` 在 `skipNextValidation` 時會把驗證結果改回目前（網址帶入）的值。也就是首次載入、變數尚未 active 時，不在選項內的網址值會被保留，不會被丟棄。

結論：`?var-board=%5C%27%29%20OR%201%3D1%20--`（或 var-min_score 帶反斜線）很可能在首次載入就被帶進 SQL；開發規格 7.25 與威脅表把這當主要防線，與此證據矛盾。我未能用真瀏覽器證明，所以標「很可能」，但「沒有任何可靠防線」本身就足以讓條件 2 不成立：工人自己在回報也寫了沒有實測。

另外 min_score 同樣受影響：`toFloat64OrDefault(${min_score:sqlstring}, 0.5)` 內的字串也能用 `\'` 逃出（我只實測 board，min_score 的 payload 未送）。

### 問題 3：測試沒有驗到被擋住（工人回報的缺口 + 一個我找到的盲點）

1. `test_board_value_with_backslash_...` 與 `test_min_score_value_with_backslash_...` 遇到 `QueryError` 就直接 return，反斜線 payload 通過只是因為語法錯。
2. 即使沒報錯，判斷「注入成功」用 `other.board not in _text(rows)`，而 `_text` 只串接 frame 的值。「各看板推文量」是 timeseries，回傳寬表，看板名稱在欄位的 labels 裡，不在 values 裡，所以問題 1 的洩漏（`推文數` 多出一欄）斷言看不出來。這解釋了為什麼問題 1 的 payload 在 `BACKSLASH_PAYLOADS` 裡仍然全綠。
3. 整合測試的展開模擬沒有 `"` → `\"`（真的格式器有，雖然實務上無害）。

## 建議（給下一輪 A / B）

- 補回歸測試：對「各看板推文量」用 `\') OR 1=1 --` 搭配兩個看板的種子資料，斷言回傳的 frame（含欄位 labels／欄位數）不含別的看板，且不得用「報錯就放行」；先讓它紅。
- 修法需要不依賴 Grafana 前端逃脫反斜線，例如把值改用不含 `'`、`\` 的編碼再由 ClickHouse 解（`${board:percentencode}` 搭配 `decodeURLComponent`／`arrayMap`，需自行驗證多選的展開格式），或在 SQL 端以 `board IN (SELECT board FROM posts_latest WHERE ...)` 讓使用者字串只能做比對、不能出現在 SQL 結構。這是 backend 要決定的，我只確認現行寫法不成立。
- 若甲方接受「靠唯讀帳號、風險低」，要由 manager 另開 D-編號明確放行；現況不能算驗收條件 2 通過。

## 其他檢查（無問題）

- `grep` 新增內容沒有寫死的 port、網址、token（只改 radar.json 與 development-spec.md）。
- 開發規格 7.25 的變數說明已寫下拉選項、預設、說明文字與威脅表（內容的準確性見問題 2）。
- 邊界：min_score 的 4 個選項都由 test_min_score_threshold_still_applies_with_escaped_format 驗過門檻行為。

manager 補充：
- 流程：qa 先依證據檔「建議」第 1 點補回歸測試（語法正確的反斜線 payload，斷言含欄位 labels 在內不得出現選項外看板的資料；不可「報錯就放行」），並同樣涵蓋 min_score；重新鎖定後才派回 backend。
- 修法不可依賴 Grafana 前端跳脫反斜線，也不可只靠 allowCustomValue。可選方向（backend 決定並實測）：值改用不含 `'`、`\` 的編碼再由 ClickHouse 解（例如 percentencode＋decodeURLComponent），或讓使用者字串只能做比對、不進 SQL 結構；min_score 也可改用 custom 變數的 key:value 只帶固定數字。開發規格 7.25 威脅表依實際防線改寫。
- 不開 D-編號放行：先修。若證實在 Grafana 13.0.2 無法可靠防住，停下回報，由 manager 問甲方。

## 追加 2026-10-21

### reports/dashboard-min-score-select.qa.md

FAIL 0848c15

# QA：dashboard-min-score-select（commit 0848c15，驗收測試鎖定 c15d493）

結論：FAIL，1 個問題（開發規格 7.25 有兩處殘留舊說法，與實作不一致）。程式與行為層面全部通過；percentencode 的真實展開方式已驗證與測試模擬一致。依甲方指示只做靜態檢查與正常值檢查，沒送攻擊字串。

## 驗收條件逐條

| # | 條件 | 結果 |
|---|---|---|
| 1 | min_score 下拉（0.4～0.7、預設 0.5）有說明 | 通過。radar.json：type=custom、query=`0.4,0.5,0.6,0.7`、current=0.5、multi/includeAll=false、description 有寫（模型三類最高機率低於此值標為「不確定」，影響情緒分布與熱門文章排行）；acceptance 測試也驗過 |
| 2 | 使用者字串不進 SQL 結構 | 通過（靜態）。`grep` 排除 percentencode 後，radar.json 沒有任何 `$board`／`$min_score`／sqlstring 引用；全部寫成 `'${…:percentencode}'` 放在 SQL 單引號內，由 `decodeURLComponent` 解碼；靜態測試 test_every_board_and_min_score_reference_uses_percentencode 全過 |
| 3 | 驗收測試全過、單元、ruff | 通過（見下） |
| 4 | 開發規格 7.25 同步 | 未通過（問題 1） |
| 5 | PR CI 全綠 | 未驗（本輪派工未要求，未 push 前無法驗；worker 回報也註明未確認） |

## 自己執行的指令與輸出

驗收測試未被改：`git diff c15d493 HEAD --stat -- tests/integration/acceptance tests/integration/dashboard` 無輸出（c15d493 之後只動 radar.json 與 development-spec.md）。

`docker compose --env-file .env -f .worktrees/dashboard-min-score-select/compose.yaml run --rm test pytest tests/integration/acceptance/dashboard tests/integration/dashboard -q`
→ `179 passed in 18.67s`

`uv run pytest tests/unit -q`（worktree）→ `1114 passed in 3.62s`
`uv run ruff check .` → `All checks passed!`；`uv run ruff format --check .` → `252 files already formatted`

## 重點：Grafana 真實展開與測試模擬是否一致

沒有瀏覽器（Chrome 在 sandbox 啟不起來），所以不是真畫面，而是兩段實證：

1. 取出執行中 Grafana（compose 的 grafana 服務）前端 bundle `/usr/share/grafana/public/build/522.e579a60fe94dd7b6ef93.js` 的原始碼：
   - percentencode 格式器：`formatter:_=>(0,d.isArray)(_)?o("{"+_.join(",")+"}"):o(_)`；`o(S)` = `encodeURIComponent` 後再把 `!'()*` 編成 `%XX`。即「陣列先包 `{a,b}` 再整串編碼，字串直接編碼」，與測試模擬相同。
   - All 的值：`MultiValueVariable.getValue` 在 hasAllValue 且沒設 allValue 時回傳所有選項 value 的陣列（`_=this.state.options.map(x=>x.value)`），所以 All 會展開成 `{全部看板}`；radar.json 的 board 沒設 allValue。多選變數只選一個時值也是陣列，展開為 `{a}`，與 SQL 的 `trim(BOTH '{}' …)` 搭配。
   - 把 bundle 裡的 `o` 函式原樣抽出用 node 執行，與測試用的 Python `urllib.parse.quote("{"+…+"}", safe="")` 逐筆比對（`['Gossip_ing']`、`['八卦','Stock-x','a_b']`、`"0.5"`、`"0.7"`、`["a(b)!*'~ .x"]`、`['電影_2']`、`[]`）：全部 True（輸出一致）。
2. 用上述展開結果，經 compose 內 Grafana 的 `/api/ds/query`（真的 plugin、唯讀帳號 grafana；帳密為 compose.yaml 與 `_dash.py` 的測試設定）送出實際 SQL，並在獨立時間窗（2026-07-01～07-04）種 3 個看板：`Gossip_<id>`（含底線，負面 0.55）、`八卦<id>`（中文，中立 0.65）、`Sto-ck<id>`（含連字號，正面 0.75），各 1 篇文章、12 則推文（10 推 2 噓）。

看板結果（5 個含 board 的面板：各看板推文量、情緒分布、情緒趨勢、爭議度最高、熱門文章排行；每個都比對「選到的看板集合」是否完全相等，趨勢面板比對天數）：

| 情況 | 實際送出的 decodeURLComponent 字串 | 結果 |
|---|---|---|
| 單選底線 | `'%7BGossip_5c5477%7D'` | 5 個面板都只含該看板，不多不少 |
| 單選中文 | `'%7B%E5%85%AB%E5%8D%A65c5477%7D'` | 同上 |
| 單選連字號 | `'%7BSto-ck5c5477%7D'` | 同上 |
| 多選 A+B、B+C、A+C | 例 `'%7BGossip_5c5477%2C%E5%85%AB%E5%8D%A65c5477%7D'` | 剛好選到的兩個看板，趨勢 2 天 |
| All（73 個看板，用 board 變數自己的查詢取得） | `'%7BGossip_…%2C…%7D'`（全部看板） | 3 個有資料的看板全出現，趨勢 3 天 |
| 空選取 | `'%7B%7D'` | 回空（1 個空 frame），不報錯 |

每種情況輸出都是 `ALL PANELS EXACT`。

min_score 四個選項（board=All，送出的是 `toFloat64OrDefault(decodeURLComponent('0.x'), 0.5)`）：

| min_score | 看板 A（0.55 負面） | 看板 B（0.65 中立） | 看板 C（0.75 正面） | 熱門排行「情緒」 |
|---|---|---|---|---|
| 0.4 | 負面 | 中立 | 正面 | A負面 B中立 C正面 |
| 0.5 | 負面 | 中立 | 正面 | 同上 |
| 0.6 | 不確定 | 中立 | 正面 | A不確定 B中立 C正面 |
| 0.7 | 不確定 | 不確定 | 正面 | A不確定 B不確定 C正面 |

與預期（score < 門檻 → 不確定）完全相符。

限制：沒有真畫面確認前端確實把變數代入面板；展開邏輯來自 bundle 原始碼與 node 比對，不是瀏覽器實測。dashboard 的另一個前端行為（網址參數帶入選項外的值）依甲方方向不再是防線，未測。

收尾：已執行 `docker compose --env-file .env -f .worktrees/dashboard-min-score-select/compose.yaml down -v`，容器、網路、volume 都已移除。

## 問題

### 問題 1：開發規格 7.25 還有兩處舊說法，與實作不一致

檔案 `docs/development-spec.md`（worktree 0848c15）：

1. 第 1048 行（面板 SQL 說明）尾端殘留：`威脅表：，整合測試依假設的格式（多選展開成 'a','b'、單引號與反斜線跳脫、空清單展開為空字串），真正的前端展開（多選、All、含單引號的值、沒有看板）由階段收尾的 uat 以真畫面確認`。
   - 「威脅表：，」是半截句；
   - 「多選展開成 `'a','b'`、單引號與反斜線跳脫」是 sqlstring／singlequote 的舊假設，現在實作與整合測試模擬的是 `{a,b}` 整串 percentencode，且本輪已用 bundle 原始碼與 Grafana 實測確認；
   - 「由 uat 以真畫面確認」的待辦與現況（已驗展開）不符。
2. 第 1035 行（變數說明）仍寫「兩個變數都關閉 `allowCustomValue`，網址帶不在選項內的值會被丟棄」。上一輪 qa 的 bundle 分析顯示 Grafana 13.0.2 首次載入時網址值不會被丟棄（skipNextValidation），本輪方向也已改為不靠它；威脅表（第 1052 行）已正確寫成靠 percentencode。這句保留會讓讀者誤以為 allowCustomValue 是防線。

重現：`grep -n "威脅表：，\|丟棄\|'a','b'" .worktrees/dashboard-min-score-select/docs/development-spec.md` 會命中第 1035、1048 行。
修法方向（由 backend 決定）：刪除上述兩處舊句，改成「展開為 `{a,b}` 整串 percentencode，已對 Grafana 13.0.2 前端原始碼與 /api/ds/query 驗證」；`allowCustomValue: false` 若保留須註明只是 UI 層限制、不是防線。這是文件與實作不一致，依 CLAUDE.md「文件必須與程式同步」與驗收條件 4 判 FAIL。

## 其他檢查（無問題）

- 寫死的設定值：本輪差異只有 radar.json 與 development-spec.md，沒有新增 port、網址、token。
- 測試殘留 `sqlstring` 字樣只在 `_dash.py` 的 `grafana_format` 與靜態檢查的負面案例，用來證明「不允許」，不影響行為。
- 邊界：看板名含底線、中文、連字號、全部看板（73 個）、空選取、min_score 四個選項皆實測。

## 追加 2026-10-21

驗收條件 2 依 D-017 改寫（取代原本「經網址參數帶入含單引號或 SQL 片段…不可執行注入的 SQL」的動態驗證）：
- radar.json 所有 `$board`、`$min_score` 引用一律 `percentencode`，放在 SQL 單引號內，由 ClickHouse `decodeURLComponent` 解碼（min_score 再轉數字）；不得用其他格式
- 驗收只用靜態檢查加正常值檢查，不寫攻擊字串（測試與實測皆同）
仲裁 TEST_OK（reports/dashboard-min-score-select.ruling.md）；補強建議另開 backlog，不擋本單。
