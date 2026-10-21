# 派工單 dashboard-integration

- **類型**：test
- **負責**：qa
- **目標**：用 compose 的 grafana 與 clickhouse，透過 Grafana API 驗證 provisioning 的 dashboard 與每個面板查詢在真的 plugin 上可用（開發規格 7.25 派工順序 4）
- **背景**：dashboard-grafana-infra、dashboard-views、dashboard-panels 已合併（PR #100、#105、#107）。PR #107 review 列了只能在真 Grafana 驗的事項（下方驗收條件 3～6），另建議把面板 6 爭議度留空、情緒套 min_score、面板 5 alert_id 去重補成自動測試。實際畫面截圖由階段收尾的 uat 做
- **設計依據**：`docs/development-spec.md` 7.25（派工順序 4、測試環境）、7.26；`reports/dashboard-panels.review.md`「給 dashboard-integration 派工單」
- **相依**：dashboard-panels（已合併）
- **負責檔案**：
  - `tests/integration/dashboard/`
  - `docs/development-spec.md`
- **禁區**：不改 `infra/`、`src/`、`compose.yaml`、已鎖定的 `tests/integration/acceptance/`；發現 radar.json 或設定有錯就回報，不自己修；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 以 `/api/ds/query` 確認 provisioning 的 dashboard（uid radar）存在、6 個面板查詢都無錯誤
  - [ ] 時間範圍邊界內外各 2 秒的種子資料分別被納入、排除（驗 `$__timeFilter_ms` 對 DateTime64(6) 的展開，1 秒內誤差可接受）
  - [ ] board 變數讀回能列出種子看板；plugin 實際展開 `$board`（All、單選、多選）無錯誤
  - [ ] `$board`、`$min_score` 值含單引號時被跳脫或查詢失敗、不改變查詢結構；`$min_score` 非數字時面板不報錯
  - [ ] 沒有任何看板時 `board IN ()` 不讓面板報錯，或在 7.25 記為已知限制
  - [ ] 面板 6 爭議度推＋噓 < 10 留空、面板 6 情緒套 min_score、面板 5 以 alert_id 去重各有自動測試
  - [ ] `make check` 通過；`docker compose --env-file .env -f .worktrees/dashboard-integration/compose.yaml run --rm test` 全過並附輸出；交單前 down -v；PR 的 CI 全綠；7.25 標實作完成
- **驗證指令**：`make check`；`docker compose --env-file .env -f .worktrees/dashboard-integration/compose.yaml run --rm test`
- **回報檔**：`reports/dashboard-integration.json`

## 執行資訊（task.py 產生）

- Issue：#108
- 分支：`test/dashboard-integration`（從 develop 開出）
- 工作目錄：`.worktrees/dashboard-integration`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-21

manager 調整分工（qa 依 guard 只能寫「驗收測試」列的目錄）：整合測試改列為驗收測試，由 qa 寫（A），寫完鎖定；之後由 backend 當 worker：更新開發規格 7.25 標實作完成，若驗收測試抓到 radar.json 或設定的問題，回報 manager 決定是否擴範圍。qa 寫的測試預期對現有實作就會通過（驗的是已合併的行為），不必先失敗；有失敗就是發現問題，寫進回報。

- **驗收測試**：
  - `tests/integration/dashboard/`
- **負責檔案**：
  - `docs/development-spec.md`

## 追加 2026-10-21

qa 寫驗收測試時發現（reports/dashboard-integration.json）：provisioning 的 datasource 用唯讀帳號 grafana（readonly=1），經 /api/ds/query 的任何查詢都回 400 `code: 164, Cannot modify 'max_execution_time' setting in readonly mode`，連 SELECT 1 也失敗；7.25「native、max_execution_time 固定 60 就能過」的結論不成立（只驗到 health check）。驗收測試已鎖定，39 個因此失敗。

backend 要做：
1. 找出根因並修好，讓 `tests/integration/dashboard/` 全過，且已鎖定的 `tests/integration/acceptance/dashboard/` 仍全過。
2. 偏好的修法：`grafana.xml` 對 `max_execution_time`（及 plugin 實際會帶的其他設定）加 constraints 的 `changeable_in_readonly`，並設上限（不超過現在 profile 的 60 秒）；或讓 datasource／Grafana 的逾時設定與 profile 一致，讓 plugin 不帶不同的值。
3. 不可用的修法：拿掉 readonly、改用管理帳號、放寬 allow_databases 或記憶體上限。若只有這類修法可行，停下來回報（屬權限與安全，要問甲方）。
4. 更新開發規格 7.25：修正上述結論、記錄實測；「dashboard 測試不需 xdist_group」那句改成現況（cdc 測試模組會 TRUNCATE radar，dashboard 整合測試標 shared_radar_db）。
5. `make check` 通過；`docker compose --env-file .env -f .worktrees/dashboard-integration/compose.yaml run --rm test` 全過並附輸出；交單前 down -v。不可改驗收測試，覺得測試錯就回報 disputes。

- **負責檔案**：
  - `infra/clickhouse/users.d/grafana.xml`
  - `infra/grafana/provisioning/`
  - `docs/development-spec.md`

## 追加 2026-10-21

### reports/dashboard-integration.qa.md

FAIL cab9595

# dashboard-integration 驗證（commit cab9595，測試目錄自 aec4eee 起無變動）

## 結論

修法本身（grafana.xml constraints＋queryTimeout 30）驗證成立；但同一組 Grafana 重複跑會被登入鎖定，連跑第二次失敗（問題 1），另有一次 Kafka 測試 flake（問題 2）。共 2 個問題。

## 逐項

| 項目 | 結果 |
|---|---|
| `git diff aec4eee HEAD -- tests` | 空（驗收測試未被改） |
| make check | pre-commit 全過；`1110 passed in 4.54s` |
| compose test，全新堆疊 `-n 0`（`pytest tests/integration -n 0`） | `308 passed in 140.47s` |
| compose test，全新堆疊 `-n auto --dist loadgroup`（down -v 後重跑） | `308 passed in 56.51s` |
| 含 tests/integration/dashboard 與 acceptance/dashboard | 在上列 308 內；另單獨跑 `158 passed in 16.71s`（重用堆疊第一次） |
| PR #109（head cab9595）CI | Check、Integration Test、Security 皆 SUCCESS |
| 7.25 與實作一致 | 一致：constraints 1～60 + changeable_in_readonly、queryTimeout '30'、native、xdist_group("shared_radar_db") 現況都與 diff 相符；進度表標實作完成 |
| 做完 down -v | 已做（最後一次已確認網路、volume 全移除；探測用暫存檔已刪，worktree `git status` 乾淨） |

## 唯讀帳號手動探測（直接對 ClickHouse HTTP，帳號 grafana）

- CREATE TABLE、INSERT、ALTER ... DELETE、TRUNCATE、DROP（radar.alerts）：全回 164 `Cannot execute query in readonly mode`
- CREATE DATABASE：497 ACCESS_DENIED
- max_execution_time=61 → 452 `shouldn't be greater than 60`；=0 → 452 `less than 1`；`SET max_execution_time=600` → 452；=1／30／60 → 200
- readonly=0、readonly=2 → 164 `Cannot modify 'readonly' setting in readonly mode`
- max_memory_usage 調高 → 164
- 其他 DB：`SHOW DATABASES`／system.databases 只見 radar；system.tables 查 default／system／information_schema 皆 0 列；`default.*` 查詢回 60/404 不存在（allow_databases 另由 acceptance 的 other_database 測試以真的第二個 DB 驗證，已過）
- postgresql()、url() 表函式：497 拒絕；file('/etc/passwd')：拒絕；system.users、system.query_log：497 拒絕
- 錯誤密碼：516 驗證失敗

## FAIL 的問題

### 問題 1：同一組堆疊重複跑，dashboard 整合測試被 Grafana 登入鎖定（401）

acceptance 的 `test_grafana_rejects_anonymous_and_wrong_password` 與參數化的錯誤密碼測試（test_grafana_infra.py:172-175、274）會對 admin 連續登入失敗，觸發 Grafana 暴力破解防護；之後 `tests/integration/dashboard/` 用 admin 打 API（`_dash.load_dashboard`）回 `401 Invalid username or password`。重現（不 down -v、連續跑）：

1. `docker compose --env-file .env -f .worktrees/dashboard-integration/compose.yaml run --rm test pytest tests/integration -n auto --dist loadgroup -q`（通過）
2. 同堆疊再跑 `... pytest tests/integration -n 0 -q --tb=line`：`EEEE...` 約 49 個 dashboard 測試 setup error，全是 `provisioning 的 dashboard radar 讀不到：401`
3. 同堆疊再跑 `... pytest tests/integration/acceptance/dashboard tests/integration/dashboard -n 0 -q --tb=line`：第一次 158 passed，緊接第二次 `109 passed, 49 errors`，錯誤相同

down -v 後重跑即恢復，所以只影響不拆堆疊的連跑，不影響 CI；但 7.26 寫「連跑兩次也過」，這條現在不成立。需要決定：dashboard 測試改用不受鎖定影響的方式（例如 Grafana 設定關閉 brute-force 保護的測試環境變數，或錯誤密碼測試改用不存在的使用者名稱）、或在 7.26 記為已知限制。請補成自動測試：同一堆疊連續跑 dashboard 與 acceptance 兩次，第二次也要過。

### 問題 2：第一次全新堆疊 `-n auto` 有一個 Kafka 測試失敗（flake）

`tests/integration/common/test_producer_partition.py::test_list_tasks_land_in_assigned_partitions`：`KafkaException UNKNOWN_TOPIC_OR_PART`（建 topic 後立刻 `partition_count` 用 5 秒 timeout 查 metadata 查不到），`1 failed, 307 passed in 54.59s`。同樣指令再跑與 down -v 後全新堆疊重跑皆 308 passed，故為偶發；與本單改動（Grafana／ClickHouse 設定）無關，但回報稱「308 passed」未提到。建議另開單處理（建 topic 後等 metadata 可見），本單可由 manager 決定是否因此退件。

## 未驗證／限制

- 真前端的 `$board`、`$min_score` 展開與畫面截圖仍待 uat（派工單已註明）

manager 補充：
- 問題 2（Kafka 偶發 UNKNOWN_TOPIC_OR_PART）與本單無關，另開 backlog，本單不處理。
- 問題 1（admin 登入鎖定）：qa 先補一個回歸測試（測試環境中錯誤密碼嘗試之後，正確帳密仍能登入／整合測試仍能取得認證），鎖定後由 backend 修。修法限測試環境（根目錄 `compose.yaml` 的 grafana 或測試端認證方式），開發環境 `infra/docker-compose.yaml` 的登入防護不可關；錯誤密碼仍須被拒（已鎖定的 acceptance 測試）。同一組堆疊不 down -v 連跑兩次都要全過，附輸出。

- **負責檔案**：
  - `infra/clickhouse/users.d/grafana.xml`
  - `infra/grafana/provisioning/`
  - `compose.yaml`
  - `docs/development-spec.md`

## 追加 2026-10-21

### reports/dashboard-integration.review.md

REQUEST_CHANGES 7d27217

# dashboard-integration review（PR #109，head 7d27217）

## 結論

程式與設定的修法正確、安全面可接受，不需 D-編號；要退回的是 `docs/development-spec.md` 的三處：7.25、7.26 的結論還沒更正完，其中一處仍寫著「已驗證」，但實際沒驗到（和原本「health check 過就當可用」是同一類誤判）。只改文件，不必改程式或測試。

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 改動範圍 | `gh pr diff 109`：`compose.yaml`、`grafana.xml`、`datasources/clickhouse.yaml`、`development-spec.md`（皆在最後一則追加的負責檔案內）＋ `tests/integration/dashboard/`（qa 寫）。`infra/docker-compose.yaml`、`src/`、已鎖定的 `tests/integration/acceptance/` 都沒動 |
| 最後一個 commit（9418264..7d27217） | 只有 `compose.yaml` +2、spec +1 |
| `TODO(dashboard-integration)` | 沒有結果 |
| CI | Check、Integration Test、Security 皆 pass |
| 寫死設定 | 只有測試 compose 的固定測試值（跟既有的 `GF_SECURITY_ADMIN_PASSWORD: it` 同一套做法，7.25 測試環境表有寫）；`queryTimeout '30'` 是設計值，不是環境設定 |

## 特別判斷的項目

### 1. `changeable_in_readonly` 的放寬範圍（grafana.xml）

- **只放寬 `max_execution_time`**：`<constraints>` 裡只有它；其他設定仍受 `readonly=1` 擋。qa 實測 `readonly=0/2`、`max_memory_usage`、`SET`／`SETTINGS` 改其他值都回 164
- **上下限合理**：`max 60` 等於原本 profile 的固定值，查詢時間的上限沒有放寬；`min 1` 擋掉 `0`（0 代表不限時間，qa 實測 `=0` 回 452），這條一定要留著
- **其他繞過 readonly 的路**：
  - 要換 profile 得改 `profile` 設定，readonly 下改不了
  - `allow_databases` 不變
  - 寫入、DDL、表函式（`url`／`postgresql`／`file`）、`system.users` 都被拒（qa 第 1、2 輪探測）
  - 沒有加 `<grants>` 或 `access_management`

  沒找到其他繞過的路
- **對開發環境的影響**：`infra/docker-compose.yaml` 也掛同一個 `grafana.xml`，所以開發環境一起套用。這次的變更只是讓唯讀帳號可以在 1～60 秒內**調低**逾時，權限（能讀什麼、能做什麼、資源上限）都沒擴大，不屬於決策分級④，**不需要 D-編號**。修好之前，開發環境的 dashboard 其實每個查詢都失敗（7.25 原本的誤判），這次一起修好
- `queryTimeout: '30'` 低於上限 60；datasource 是 provisioning 管理，UI 改不動，只有改檔案才能突破上限，而突破了查詢會直接失敗（452），不會默默放寬

### 2. 測試環境關閉登入防護（compose.yaml）

- 只加在根目錄 `compose.yaml`（檔頭寫明只給整合測試用，Makefile 只有 `test-int` 用它；開發用的 `make up` 用 `infra/docker-compose.yaml`，裡面沒有這個旗標）
- 測試的 grafana 只接 internal network、不開 port；CI 疊加 `compose.ci.yaml` 時只綁 `127.0.0.1`，帳密是測試用固定值，而且 runner 用完就丟。關掉防護的範圍可以接受
- 錯誤密碼仍然回 401（acceptance 的錯誤密碼與匿名測試照樣通過，qa 也手動試了 12 次都是 401）
- 回歸測試 `test_zz_login_lockout.py` 自己送 12 次錯誤密碼再登入，不靠 acceptance 測試的執行順序，平行執行時也成立

### 3. qa 整合測試的品質

- **xdist_group**：每個模組都標 `shared_radar_db`，跟 `cdc/test_clickhouse_migrations.py`（模組開始時會 TRUNCATE radar）同一組，理由正確。lockout 測試不碰 DB，標了也沒有壞處
- **時間邊界**：邊界內外各 ±2 秒，`$__timeFilter_ms` 由後端 plugin 真的展開，這條驗到了
- **面板回歸**（爭議度 <10 留空、=10 邊界、情緒套 min_score、alert_id 去重、超過 24h 排除）：斷言都直接對應 PR #107 review 的建議，有正向也有反向
- **注入測試**：都先跑一次對照組（用正常值必須查得到東西），所以「查詢失敗就算過」不會因為 plugin 整個壞掉而默默通過；SQL 裡沒有 `$board` 時，對照組本身就會失敗
- **限制：前端展開是模擬的**。`$board`、`$min_score` 是 Grafana 前端代換的，`/api/ds/query` 不會展開。`_dash.expand_vars`／`quote` 用的是 qa 自己假設的格式（多選展開成 `'a','b'`、反斜線跳脫），所以測試證明的是：
  - 照這個格式代換後，SQL 在真的 plugin 加 ClickHouse 上可用
  - 跳脫不足時，ClickHouse 端會讓查詢失敗，或至少不會多回資料

  它**沒有**證明 Grafana 前端真的照這個格式展開（多選格式、跳脫方式、All 的展開、沒有任何看板時展開成什麼）。驗收條件 3 寫的「plugin 實際展開 `$board`」只驗到上面這一半；另一半要等 uat 用真前端確認。測試本身沒寫錯（`_dash.py` 的 docstring 也寫明了），問題在文件，見下方第 1 條

### 4. 7.25 結論更正是否完整

- 1057 行（native、constraints、queryTimeout、health check 誤判）：完整，與 diff 一致
- 1081 行（登入防護）、1082 行（xdist_group 現況）：與實作一致
- 還有三處沒更正，見下方

## 要修改（逐條）

1. `docs/development-spec.md:1048`
   - **問題**：寫「plugin 實際展開的結果由 `dashboard-integration` 驗證」。實際上本單只驗了後端 macro（`$__timeFilter_ms`、`$__timeInterval`）；`$board`、`$min_score` 是前端代換的，本單用 `_dash.expand_vars` 模擬。文件說「驗到了」，其實沒驗到
   - **要怎麼改**：改成「`$__timeFilter_ms`、`$__timeInterval` 由 `dashboard-integration` 經 `/api/ds/query` 驗證；`$board`、`$min_score` 由 Grafana 前端代換，整合測試依假設的格式（多選展開成 `'a','b'`、單引號與反斜線跳脫、空清單展開為空字串）模擬，真正的前端展開（多選、All、含單引號的值、沒有看板）由階段收尾的 uat 以真畫面確認」
2. `docs/development-spec.md:1093`（派工順序第 4 列）
   - **問題**：還寫著「另以 `make up` 後的截圖當驗收證據」，負責欄是 qa；但 364 行進度表寫「畫面截圖由階段收尾的 uat 做」，派工單也這樣寫。同一件事兩處寫法不一致
   - **要怎麼改**：把第 4 列的截圖那句改成「畫面截圖與真前端變數展開由階段收尾的 uat 做」（或直接引用第 1 條的那句）。負責欄照實際分工寫（qa 寫測試＋backend 修設定），或請 manager 決定怎麼寫
3. `docs/development-spec.md:1173`（7.26 平行隔離表，radar DB 那一列）
   - **問題**：寫「只有 `cdc/test_clickhouse_migrations.py` 用」radar DB，跟 1082 行矛盾，因為 dashboard 的整合測試和 acceptance 測試都在 radar 放種子資料。另外，已鎖定的 `tests/integration/acceptance/dashboard/test_views.py`、`test_panels.py` 模組說明寫「不需要 xdist_group」、也沒標，平行執行時一樣可能被 cdc 模組的 TRUNCATE 清掉種子資料（目前沒觀察到，但有這個風險）
   - **要怎麼改**：
     - 這一列改成：「使用者有 cdc 模組（會 TRUNCATE）與 dashboard 整合測試（同組 `shared_radar_db`）；acceptance/dashboard 的種子資料也放在 radar、但沒分組，有被 TRUNCATE 清掉的風險」
     - 在 open_questions 回報 manager：acceptance 測試鎖定了，要不要開單由 qa 補標 `xdist_group`

## 給 manager（不擋這次合併的理由）

- acceptance/dashboard 沒分組的潛在 flake（第 3 條）要修得改已鎖定的測試，worker 不能動，建議另開單給 qa
- 真前端的 `$board`／`$min_score` 展開要列進階段 7 uat 的檢查項（多選、All、沒有看板、看板名稱含單引號）
