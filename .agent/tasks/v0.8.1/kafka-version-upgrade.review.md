APPROVE 02edee3

# Review PR #229（kafka-version-upgrade）

## 檢查項目

| 項目 | 結果 | 依據 |
|---|---|---|
| 變更範圍 | 通過 | `gh pr diff 229`：只有 `.env.example` 一行 `KAFKA_VERSION=4.1.0` → `4.1.2`；commit 只有 `02edee3`，沒有碰負責檔案以外的檔案 |
| 與 D-034、7.28 C、派工順序第 3 列一致 | 通過 | D-034 選 A（4.1.2）；7.28 派工順序第 3 列的負責檔案就是這一行 |
| 寫死設定 | 無 | 版本只在 `.env.example`；`compose.yaml:7` 與 `infra/docker-compose.yaml:53,70,87` 用 `${KAFKA_VERSION}` 取值 |
| CI 以新版全綠 | 通過 | run 40828993062：Check、Integration Test、Security 都是 SUCCESS。Integration Test 的 `Detect code changes` 判定要跑，`Prepare env`（`ci.yml:87`）把 `.env.example` 複製成 `.env`，`Pull images` 用 `compose.yaml` 拉 kafka，`1984 passed in 135.70s`。所以整合測試跑的是 4.1.2 |
| 本機整合測試 | 有跑 | worker 回報 `371 passed`，`images kafka` 顯示 `apache/kafka:4.1.2`，跑完已 `down -v` |
| 文件同步 | 不需要 | 設計文件與開發規格裡沒有其他寫死 4.1.0 的地方要改（設計文件 424 行寫的是「Kafka 4.1」） |
| 安全 | 沒有問題 | 同一個小版本的修正版，沒有改 compose、Dockerfile、volume |

## 7.28 C 的逐台升級步驟夠不夠 manager 照做

結論：可以照做，不會刪資料。下面兩點不擋這個 PR（`docs/` 不在本單的負責檔案內），建議 manager 照下面的寫法做，下次改文件時順便補上。

| 項目 | 現況 | 判定 |
|---|---|---|
| 不刪資料 | `KAFKA_LOG_DIRS=/var/lib/kafka/data` 掛在具名 volume `kafka_N_data`。`up -d` 重建容器時會保留具名 volume | 安全；不要用 `down -v` 或 `rm -v` |
| 只動一台 | kafka_1～3 沒有 `depends_on`，`up -d kafka_N` 只會重建指定的那一台 | 安全 |
| 單行指令 | 升級步驟寫成 `docker compose … up -d kafka_N`，`…` 省略了參數 | 要寫完整：`docker compose -f infra/docker-compose.yaml --env-file .env up -d kafka_1`（kafka_2、kafka_3 同樣寫法） |
| 「等 healthy」怎麼確認 | 沒寫指令；而且 healthcheck（`kafka-broker-api-versions.sh`）只確認 broker 有回應，不代表副本已經追上 | 換下一台前要再確認兩件事：① `docker compose -f infra/docker-compose.yaml --env-file .env ps kafka_1` 顯示 `(healthy)`；② `docker compose -f infra/docker-compose.yaml --env-file .env exec kafka_1 /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:29092 --describe --under-replicated-partitions` 沒有輸出。如果第一台還沒回到 ISR 就停第二台，部分 partition 的 ISR 只剩 1 份，低於 `min.insync.replicas=2`，acks=all 的寫入會失敗。7.28 C 寫的「一次停一個不影響寫入」要等副本追上才成立 |
| 狀態文字 | 7.28 C 還寫著「升到 4.1.2：待甲方決定（D-034）」 | D-034 已經定案，這句過時了，manager 更新進度時一起改 |

## 問題數

擋 PR 的問題 0 個；給 manager 的文件建議 3 個（單行指令寫完整、換下一台前確認副本追上、狀態文字過時）
