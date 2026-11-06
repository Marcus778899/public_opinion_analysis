APPROVE 141c32f

# Review：grafana-readonly-verify（PR #249）

## 檢查範圍

| 項目 | 結果 |
|---|---|
| diff（`gh pr diff 249`，對 develop） | 只有新檔 `tests/integration/dashboard/test_grafana_readonly.py`（+157），在負責檔案內；`grafana.xml` 未動，沒碰禁區 |
| 驗收條件 1～4 | 讀、寫／DDL、system、table function 都有測試；qa 跑過 234 passed、`make check` 通過 |
| 寫死設定 | 只讀 `IT_CLICKHOUSE_URL`、`CLICKHOUSE_GRAFANA_USER`／`PASSWORD`，預設值 `grafana`／`it` 是 compose 的測試值，寫法與 `acceptance/dashboard/test_grafana_infra.py` 相同 |
| 安全與 bug | 沒有阻擋問題；有 2 個非阻擋項目（見下方） |

## 我在 worktree 的 compose（ClickHouse 26.8.19）補做的實測，做完已 `down -v`

| 帳號／readonly | `url()` | `file()` | `system.users` |
|---|---|---|---|
| grafana（profile readonly=1） | 497 缺 READ ON URL | 497 缺 READ ON FILE | 497 |
| radar，session readonly=1 | 164 READONLY | 164 READONLY | 可讀 |
| radar，session readonly=2 | 198 DNS 失敗（**放行**） | 107 檔案不存在（**放行**） | 可讀 |
| radar，readonly=0 | 放行 | 放行 | 可讀 |

`system.grants` 顯示 grafana 有全域 `SOURCES`、`READ`、`URL`、`FILE`；SHOW GRANTS 也列了 `SYSTEM SHUTDOWN`、`KILL QUERY`、`CREATE FUNCTION` 等全域權限。

結論：
- table function 被擋，靠的是 `readonly=1`。readonly=2 時 url()、file() 就能用了。qa 的更正成立，worker 回報說「沒授予權限」是錯的。
- 敏感的 system 表被擋，靠的是 `allow_databases` 收斂後的授權，和 readonly 無關。radar 在 readonly=1 下照樣讀得到 `system.users`。所以 7.25 要分兩條寫：table function 寫「靠 readonly=1」，system 表寫「靠 allow_databases」。qa 證據的「注意事項」把兩者合在一起寫，不夠精確。

## 問題一：readonly 回歸防線有沒有鎖住

有，但是靠行為間接鎖住，沒有直接斷言設定值。

| profile 被改成 | 會不會被抓到 | 由哪個測試抓到 |
|---|---|---|
| 拿掉 readonly（0） | 會 | 寫入與 DDL 的參數化測試、`test_readonly_setting_cannot_be_lifted_by_query` |
| readonly=2 | 會 | `test_external_access_table_functions_are_denied`：url()、file() 會回 DNS 或檔案錯誤，不是 ACCESS_DENIED；`executable` 那題也不會再回 READONLY。寫入題與 `SET readonly=0` 題在 readonly=2 下仍然通過，抓不到 |

非阻擋建議（可以另開單，或併進下一張碰這個檔的單）：
1. `tests/integration/dashboard/test_grafana_readonly.py:89-92` — 只鎖了 `max_execution_time`，沒鎖 readonly 本身 — 加一行 `assert rows("SELECT getSetting('readonly')") == ["1"]`。這樣 readonly=2 的回歸會直接失敗並指出原因，不用等 table function 那題在 DNS timeout（最長 60 秒）後才失敗。
2. `tests/integration/dashboard/test_grafana_readonly.py:118-123` — `test_system_settings_do_not_expose_credentials` 是空測試：26.8 根本沒有 `s3_access_key_id`、`s3_secret_access_key` 這兩個設定（我實測查回 0 列），`all([])` 永遠是 True — 先斷言查得到列，否則改測真的存在的項目，或刪掉這題。

## 問題二：SOURCES 要不要另開 backlog 收緊

建議開，優先度低，不擋這張單。

- 理由：防線只有一層。grafana 帳號除了 SELECT radar.*，還有全域的 SOURCES 與多項 SYSTEM、KILL、CREATE FUNCTION 權限，目前全靠 profile 的 `readonly=1` 擋住。只要有人為了 Grafana 某個功能把 readonly 改成 2，url()、file() 就會重新開放（上表已實測）。
- 範圍：不要只處理 SOURCES，要把 grafana 的有效權限收斂到 `SELECT, SHOW ON radar.*`。可行做法是 XML `<grants>` 或 SQL 管理的帳號，但開發規格 7.25 刻意不用 `<grants>`，原因是 26.8 的行為查不到官方說明、26.9 的 users.xml grants 有問題。所以這張 backlog 要先調查，再改設定。
- 分級：這是權限設定的變更（決策分級④），而且本輪範圍沒列。要不要排進本輪，由 manager 判斷是否要開 D-編號。

## 開發規格 7.25 回寫（給 manager，本單禁改規格）

- 威脅表的「唯讀帳號」一列改寫成兩條：
  - table function：靠 `readonly=1`，readonly=2 就會重新開放（已實測）
  - 敏感 system 表：靠 `allow_databases`
- 註明 `test_grafana_readonly.py` 是升版與改設定時的回歸防線。
- 要更正 worker open_questions 第 5 條「未授予 READ 權限」的說法。
