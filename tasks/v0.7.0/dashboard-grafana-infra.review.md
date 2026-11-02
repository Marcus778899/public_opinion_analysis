APPROVE 4a2a4f0

# Review dashboard-grafana-infra（PR #100，第 2 輪）

對照：派工單（負責檔案以最後一則追加為準）、開發規格 7.25「部署與權限／威脅與對策／測試環境／test_grafana_infra.py 要驗的」、7.26 做法表與風險表、D-014、backend-standards 第 5、6 節。整個 PR 重新看過（`origin/develop...4a2a4f0`），不只看上一輪的 4 點。

## 上一輪 4 點（REQUEST_CHANGES ebc8937）

| # | 位置 | 判定 |
|---|---|---|
| 1 | `infra/docker-compose.yaml:352` image tag | 已修：`radar-grafana:${GRAFANA_VERSION}-${GRAFANA_CLICKHOUSE_PLUGIN_VERSION}`，只升 plugin 也會換 tag、`make up` 會重建 |
| 2 | `infra/docker-compose.yaml:356` GRAFANA_PORT | 已修：`${GRAFANA_PORT:?GRAFANA_PORT 未設定}` |
| 3 | 開發規格 7.26 做法 1、2、7、10 與風險表 grafana.xml 一列 | 已修：做法 7 改成掛三個檔並引用 7.25；做法 2 必填清單補 `IT_GRAFANA_URL`；做法 10 改四個服務與 `up` 清單；風險表改成「已處理」並引用，沒有重寫 7.25 |
| 4 | 開發規格 364、605、1014，設計文件 582 | 已修：都改成引用 D-014，1014 標「已定案：A，見 D-014」並保留比較當紀錄 |

## 整體檢查

| 項目 | 判定 |
|---|---|
| 改到負責檔案以外 | 沒有：19 個檔都在清單內；`tests/**/acceptance/` 只有 qa 的 8b1488f，`git diff 8b1488f HEAD -- tests/unit/acceptance tests/integration/acceptance` 無輸出；sync 帶進來的 certifi 升版（`uv.lock`、`pyproject.toml`）不在 PR diff |
| compose.yaml（受保護路徑） | 通過：`grafana` 只接 `grafana_offline`（`internal: true`）、沒有 `ports`、沒有 docker socket；volume 只有 provisioning、dashboards 兩個唯讀掛載，資料放 tmpfs；`clickhouse` 只多單檔掛 `grafana.xml`；`clickhouse`、`test` 接兩個 network；`test` 多 `IT_GRAFANA_URL` 與測試固定值，符合 7.25 測試環境各列 |
| compose.ci.yaml | 只在 CI 讓 grafana 另接 default、綁 `127.0.0.1:${IT_GRAFANA_HOST_PORT:?}`；NOTE 寫明 CI 不構成離線證據，與 7.25「離線檢查的限制」一致 |
| 開發 compose | 只綁 127.0.0.1；admin 密碼、唯讀帳密、版本都 `${…:?}`；關閉匿名與註冊；depends_on clickhouse healthy；新 volume `grafana_data` |
| 唯讀帳號 `grafana.xml` | `readonly=1`、`allow_databases` 只有 `from_env` 的 `CLICKHOUSE_DB`、沒有 named collection 權限、`max_execution_time`／`max_memory_usage` 有上限、密碼 `from_env`；對應威脅表第 2、3 列。實際行為由 `test_grafana_infra.py` 的唯讀帳號、設定載入兩項驗證（qa 22 項過） |
| Dockerfile | 版本由 build arg 帶入、plugin 裝在 `/opt/grafana-plugins`、關閉 preinstall／自動更新／更新檢查與回報，以 uid 472 執行；時區 `Asia/Taipei` 符合 7.25 |
| provisioning | datasource 固定 uid `radar-clickhouse`、`editable: false`、帳密走環境變數展開；dashboard provider `allowUiUpdates: false`，符合 7.25「provisioning 管理」 |
| 寫死的設定值 | 沒有：測試 compose 的 `it` 密碼是 7.25 規定的測試固定值；開發 compose 全部走變數；新變數都在 `.env.example`（上一行有說明） |
| CI | `up -d --wait` 加 grafana、export `IT_GRAFANA_URL`；`.env` 由 `.env.example` 複製，有兩個版本與 `IT_GRAFANA_HOST_PORT`；`gh pr checks 100` @ 4a2a4f0：Check、Integration Test、Security 全 pass |
| 測試有沒有測到驗收條件 | 有：靜態檢查（`tests/unit/acceptance/dashboard/`）在 `make check`（1110 passed）；`test_grafana_infra.py` 22 項在 `run --rm test`（Grafana 只接 internal network，離線證據成立）與 CI 都跑；`conftest.py` 必填清單加 `IT_GRAFANA_URL`，缺就 `pytest.exit` |
| 文件同步 | 開發規格 1.3、7.25（選定版本與理由、native 協定限制）、7.26，設計文件 9.1、10.3、11.1 都已同步 |
| `grep -rn "TODO(dashboard-grafana-infra)" src tests infra` | 無結果 |

## 非阻擋（給 manager，與上一輪相同，仍成立）

- e2e（`infra/docker-compose.e2e.yaml`，不在本單負責檔案）沒有覆寫 grafana：`make e2e-up` 會沿用 `radar_grafana` 容器與開發的 `grafana_data` volume。影響小（只有登入狀態），建議另開 issue 加 `e2e_grafana_data`。
- `dashboard-panels` 派工單要寫明：面板 SQL 不可用 `SETTINGS` 子句（readonly=1 會拒絕）；plugin 帶的設定只在 `dashboard-integration`（`/api/ds/query`）驗得到。
- 合併後甲方需依 `.env.example` 在 `.env` 補 7 個新變數（worker 回報 open_questions 第 1 點），否則 `make up` 與 `run --rm test` 會因 `${:?}` 失敗；`make up` 時開發的 clickhouse 會重建以載入 `grafana.xml`（資料在 volume，不受影響）。

問題數量：0
