APPROVE 2698314

# Review：PR #124 dashboard-min-score-select（相對 develop 的整個 diff，HEAD 2698314）

結論：程式與文件可合併，沒有要改的地方。**合併前要先處理的事**：PR 在 2698314 的 CI「Integration Test」紅了，失敗的測試跟這張單無關（見下面「CI」），請 manager 重跑失敗的 job，綠了才算達成驗收條件 5。

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 負責檔案 | worker 的 commit（ff499e6、148267e、0848c15、2698314）只動 `infra/grafana/dashboards/radar.json`、`docs/development-spec.md`。diff 裡的 `tests/integration/acceptance/dashboard/`、`tests/integration/dashboard/` 是 qa 的 `test(...)` commit（61181af、f5f6b32、c15d493），都在派工單的驗收測試目錄裡。沒有碰到 `src/`、provisioning、compose |
| D-017：引用格式 | radar.json 的變數引用只有 `${board:percentencode}` 11 處、`${min_score:percentencode}` 5 處，全部放在 SQL 單引號裡，外面包 `decodeURLComponent(...)`。沒有 `$board`、`[[...]]`、`sqlstring`、`singlequote`、`IN ($board)` 殘留。percentencode 的輸出只有 `A-Za-z0-9-_.~%`，不會跳出字串，也不會產生 `\` |
| SQL 正確性：board | `has(splitByChar(',', trim(BOTH '{}' FROM decodeURLComponent(...))), board)`。單選、多選、All 都會展開成 `{a,b}`；空選取展開成 `{}`，結果是 `['']`，比對不到，回空。PTT 看板名稱不會有 `,`、`{`、`}`，所以切開的結果正確。5 個含 board 的面板（各看板推文量、情緒分布、情緒趨勢、爭議度、熱門排行）裡，每個子查詢和外層 WHERE 都換掉了，沒有漏 |
| SQL 正確性：min_score | 面板 2 的 4 處與面板 6 的 1 處都是 `toFloat64OrDefault(decodeURLComponent('...'), 0.5)`，非數字時退回 0.5，跟 7.25 寫的一致；比較運算子與門檻的語意沒有變（`>=` 歸類、`<` 為不確定） |
| 查詢邏輯沒有越界 | 除了變數引用以外，各面板的 JOIN、GROUP BY、LIMIT、過濾條件跟 develop 逐字相同（禁區「不改面板的查詢邏輯」有遵守） |
| 變數定義 | `min_score`：type=custom、`0.4,0.5,0.6,0.7`、current 0.5、multi/includeAll false，有 description（給一般使用者看的說明，內容符合派工單的背景說明）。`board` 加了 `allowCustomValue: false`，只是 UI 層的限制，7.25 也如實寫明這不是防線。JSON 格式正確（`json.tool` 通過） |
| 開發規格 7.25 同步 | 變數說明（下拉選項、預設、說明文字、allowCustomValue 不是防線）、面板 SQL 的展開寫法、新的威脅表（L-5 對策＝percentencode＋在 ClickHouse 解碼＋靜態測試），都跟 radar.json 一致；qa 0848c15 指出的舊說法已經移除。`docs/security/v0.7.0.md` 裡的舊行號與舊寫法是資安報告的歷史紀錄，不是這張單的檔案，不要求同步 |
| 寫死的設定 | 沒有新增 port、網址、token |
| 程式碼規範 | 只有 JSON 與文件，沒有 Python 的變更；ruff、單元測試、pre-commit 由 qa 2698314 跑過，全部通過 |
| `TODO(dashboard-min-score-select)` | `grep -rn "TODO(dashboard-min-score-select)" src tests infra docs` 沒有結果 |
| 測試有沒有測到驗收條件 | 條件 1：acceptance `test_min_score_variable_is_dropdown_...`。條件 2（依 D-017 改寫）：兩個 `test_every_board_and_min_score_reference_uses_percentencode` 的靜態規則，加上正常值測試（中文、底線、多選、四個門檻）。qa 另外用 Grafana 13.0.2 的 bundle 和 `/api/ds/query` 驗證過展開結果。仲裁結果是 TEST_OK |

## CI

`gh pr checks 124`（2698314）：Check pass、Security pass、**Integration Test fail**。

- 失敗的測試：`tests/integration/common/test_topics_apply.py::test_apply_updates_changed_retention_and_partitions`，錯誤是 `assert 3 == (3 + 1)`（Kafka 增加 partition 後馬上讀，讀回來還是舊的值）。結果是 1 failed、1442 passed
- 判斷跟本單無關：這張單沒有改到 `src/`、`tests/integration/common/`；0848c15 跟 2698314 的差別只有 `docs/development-spec.md` 4 行，radar.json 完全相同，而 0848c15 的 CI 是 success。看起來是 Kafka metadata 最終一致性造成的 flaky test
- 要怎麼處理：manager 重跑失敗的 job（`gh run rerun 39559276786 --failed`），綠了才合併；另外建議開一個 issue 修這個 flaky test（在 `fetch_existing` 之前等 partition 數變成預期值）。不需要退回 worker

## 不擋合併的觀察

| 檔案:位置 | 觀察 | 建議 |
|---|---|---|
| `radar.json` 各面板的 `has(...)` | 原本的 `board IN (...)` 換成 `has(const_array, board)` 以後，可能用不到 `board` 的主鍵索引。7.25 寫明目前資料量小，不影響現況 | 之後面板變慢時，再考慮改成 `board IN (SELECT arrayJoin(...))` |
| 靜態測試沒有斷言 `in_string`、`P_VOLUME` 的 labels 沒檢查到 | 仲裁已經列出來，已開成 backlog #125 | 照 #125 處理 |
