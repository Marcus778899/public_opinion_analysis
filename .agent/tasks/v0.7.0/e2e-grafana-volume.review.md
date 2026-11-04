APPROVE 19b1e8d

# e2e-grafana-volume review（PR #114）

## 檢查項目

| 項目 | 結果 | 依據 |
|---|---|---|
| 改動範圍 | 符合 | PR 只改 `infra/docker-compose.e2e.yaml`、`docs/development-spec.md`（負責檔案），外加 qa 的驗收測試 `tests/unit/e2e_support/test_e2e_grafana_volume.py`；`git diff 683ab15..HEAD` 沒有動到驗收測試；沒碰禁區 |
| 修正 F-1 | 符合 | e2e 覆寫 `grafana.volumes: e2e_grafana_data:/var/lib/grafana`，並在頂層宣告 `e2e_grafana_data`；compose 依容器內路徑合併，開發環境的 provisioning、dashboards bind mount 照樣保留 |
| e2e 覆寫完整（含 grafana 以外的服務） | 符合 | 以 PyYAML（會展開 `<<: *app`）照 compose 的規則（依容器內路徑覆蓋）合併兩個檔，檢查全部 21 個服務：沒有任何服務還掛著開發環境的具名 volume（app_logs、heat_state、kafka_1..3_data、postgres_data、clickhouse_data、grafana_data）。inference、heat、bot、label-stream 不在 `--profile app` 裡，但也都已覆寫 |
| 命名慣例 | 一致 | `e2e_<開發 volume 名稱>`，與 e2e_postgres_data、e2e_clickhouse_data 等相同；compose 專案前綴之後是 `radar_e2e_grafana_data` |
| 文件同步 | 符合 | 開發規格第 5 章 e2e 那條補了 Grafana（`e2e_grafana_data`）；README 第 4 步的「不碰開發資料」現在成立，不用改；7.25 那條只寫開發環境的 `grafana_data`，e2e 寫在第 5 章，只寫一次的規則沒有被破壞 |
| 寫死設定、安全 | 無問題 | 沒有新的設定值；沒有加新的 bind mount |
| 驗證 | 通過 | `uv run pytest tests/unit/e2e_support -q`：20 passed；`gh pr checks 114`：Check、Integration Test、Security 都 pass（run 39550927356） |

## 驗收測試能不能防止再犯：不夠（不擋這次合併）

新的 4 條測試只檢查 grafana。既有的 `tests/unit/e2e_support/test_e2e_volumes.py:35-41`（`test_e2e_override_never_mounts_shared_dev_volumes`）只逐一檢查 **e2e 檔裡有寫到的服務**；開發環境新增一個掛具名 volume 的服務（例如 `redis_data`），e2e 沒有覆寫它時，這條測試照樣通過。F-1 就是這樣漏掉的（grafana 本來不在 e2e 檔裡）。`test_e2e_volumes.py:16` 也只涵蓋 `app_logs`。

建議由 qa 另開一單（驗收測試目錄是 qa 的，worker 不能改），加一條通用測試：

- 逐一看開發環境 compose 的**每個服務**，套用 `test_e2e_grafana_volume.py:13` `merged_mounts` 的合併規則（依容器內路徑覆蓋），斷言合併後的來源沒有一個在 `docker-compose.yaml` 的頂層 `volumes` 裡
- 用目前的檔案跑過，結果是通過，可以直接當成回歸測試

## 其他觀察（不擋合併，記下來）

1. `down -v` 只刪到 grafana_data、沒刪到其他開發 volume，是因為 compose v2 載入時會丟掉沒有服務在用的 volume（UAT S15 的輸出也是這樣）。所以安全的前提是「沒有任何啟用中的服務引用開發 volume」，上面那條通用測試守的就是這個前提
2. 開發規格第 5 章 e2e 那條（約第 310 行）列 volume 時漏了 heat 的 `e2e_heat_state`（之前就漏了，不是這張單造成的）；之後有人改這段時可以一起補
