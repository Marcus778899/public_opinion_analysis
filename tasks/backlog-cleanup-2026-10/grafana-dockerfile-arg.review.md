APPROVE 0b62464

# Review PR #136（grafana-dockerfile-arg，head 0b62464）

| 檢查項 | 結果 |
|---|---|
| 負責檔案 | 變更只有 `infra/grafana/Dockerfile`、`tests/unit/infra/__init__.py`、`tests/unit/infra/test_grafana_dockerfile.py`，與派工單「追加 2026-10-21」的負責檔案一致；禁區（compose、`.env.example`、scripts、.claude、contracts、CLAUDE.md）沒動 |
| 偏離設計（開發規格 7.25） | 沒有。底層 image 仍是 `grafana/grafana-oss:${GRAFANA_VERSION}`，版本由 `infra/docker-compose.yaml:359` 與根目錄 `compose.yaml` 的 `${GRAFANA_VERSION:?}` build arg 傳入；沒有改 Grafana／plugin 版本 |
| 寫死設定值 | 沒有。預設值 `unset-use-compose-build-arg` 是佔位字串，不是版本號；沒傳 build arg 時會因 tag 不存在而建置失敗（fail fast），不會默默用錯版本 |
| bug／安全 | 沒發現。tag 字元合法；`ARG GRAFANA_CLICKHOUSE_PLUGIN_VERSION` 在 FROM 之後，不會觸發這個警告，不需要預設值 |
| 測試有沒有測到驗收條件 | 條件 1：qa 附 `build --progress plain` 輸出，沒有 InvalidDefaultArgInFrom，image `radar-grafana:13.0.2-4.23.0`，plugin 層 CACHED（版本不變）。條件 2：`test_from_args_in_dockerfile_all_have_default` 讀真的 Dockerfile，另兩個測試確認偵測邏輯（缺預設值會抓到、有預設值會放過），用改之前的 Dockerfile 跑會失敗。條件 3：`make check` 1117 passed；PR CI（Check、Integration Test、Security）全綠 |
| 文件同步 | 開發規格 7.25 描述的是底層 image 與版本來源，行為沒變，不需要改 |

非阻擋觀察（不用改）：測試的 regex 只處理單行 `ARG NAME[=...]`，多階段、帶引號或 `--platform` 的寫法沒涵蓋；現在的 Dockerfile 只有一個 stage，不受影響。
