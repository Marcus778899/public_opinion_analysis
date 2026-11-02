APPROVE 5009f7b

# dashboard-integration review（PR #109，head 5009f7b，第 2 輪）

## 結論

可以合併。上一輪退回的 3 個文件問題都改好了，跟實作一致。這次是把整個 PR（develop...5009f7b）重新看過一遍，沒有發現新問題。

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 改動範圍 | 改到的檔案：`compose.yaml`、`infra/clickhouse/users.d/grafana.xml`、`infra/grafana/provisioning/datasources/clickhouse.yaml`、`docs/development-spec.md`，都在派工單最後一則追加的負責檔案裡；另有 `tests/integration/dashboard/`（qa 寫的驗收測試）。`src/`、`infra/docker-compose.yaml`、已鎖定的 `tests/integration/acceptance/` 都沒動 |
| 驗收測試鎖定 | `git diff 9418264 HEAD -- tests` 沒有差異 |
| 5009f7b 本身 | 只改 `docs/development-spec.md`（+3/-3） |
| 上一輪第 1 條（1048 行） | 已改成：後端 macro 經 `/api/ds/query` 驗證，`$board`／`$min_score` 依假設格式模擬，真前端展開由 uat 確認。跟 `_dash.expand_vars` 的實際做法一致 |
| 上一輪第 2 條（1093 行） | 「`make up` 截圖」已改成由 uat 做，並註明實際分工。跟 364 行、派工單一致 |
| 上一輪第 3 條（1173 行） | radar DB 列出的使用者已改對。`acceptance/dashboard/test_views.py:4`、`test_panels.py:7` 確實沒標 xdist_group，文件寫的是實情 |
| xdist_group | `tests/integration/dashboard/` 的 5 個模組都標了 `shared_radar_db`，與 1082 行一致 |
| 設定修法（grafana.xml constraints 1～60＋`changeable_in_readonly`、`queryTimeout '30'`） | 只放寬 `max_execution_time`，上限沒變，`min 1` 擋掉 0（不限時間）。沒有放寬 readonly、帳號、`allow_databases`、記憶體上限，權限沒擴大，不需要 D-編號（判斷理由同上一輪） |
| 關閉登入防護 | 只在根目錄的測試用 `compose.yaml`；`infra/docker-compose.yaml` 用 grep 找 `BRUTE` 沒有結果；錯誤密碼仍由 acceptance 測試驗證會回 401 |
| 寫死設定 | 只有測試 compose 的固定測試值，跟既有做法相同；`queryTimeout` 是設計值 |
| 其他文件 | 在 `docs`、README 用 grep 找 `max_execution_time`／`queryTimeout`／`readonly`，除了開發規格外沒有其他地方提到，沒有過時的說法 |
| `TODO(dashboard-integration)` | 沒有結果 |
| make check（worktree @ 5009f7b） | `1110 passed in 3.90s` |
| CI（head 5009f7b） | Check、Integration Test、Security 都是 SUCCESS；`mergeStateStatus` CLEAN |
| compose test | 本輪沒有改程式，沿用 qa 第 2 輪的實跑結果：全新堆疊 309 passed；同一組堆疊不 down -v 再跑一次也是 309 passed；`-n 0` 也過 |

## 給 manager（不擋這次合併）

- 已鎖定的 `acceptance/dashboard`（`test_views.py`、`test_panels.py`）沒標 `xdist_group("shared_radar_db")`，平行跑時有被 cdc 模組 TRUNCATE 的風險。建議另開單給 qa 補標
- 真前端的 `$board`／`$min_score` 展開（多選、All、沒有看板、看板名稱含單引號）要列進階段 7 uat 的檢查項
- 1093 行派工表第 4 列的負責欄仍是 qa、負責檔案寫「—」，實際分工只寫在驗收欄的括號裡。這只是記錄方式，manager 要的話可以之後調整
- Kafka 偶發 UNKNOWN_TOPIC_OR_PART 已列 #110
