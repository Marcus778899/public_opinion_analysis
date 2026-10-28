PASS 0b62464

# 驗證 grafana-dockerfile-arg（PR #136，commit 0b62464）

差異：`infra/grafana/Dockerfile` 只改 `ARG GRAFANA_VERSION=unset-use-compose-build-arg`（加預設值與 NOTE），另新增 `tests/unit/infra/{__init__.py,test_grafana_dockerfile.py}`。未動 compose、.env.example、scripts、.claude、contracts、CLAUDE.md，符合禁區。

## 驗收條件 1：建置無 InvalidDefaultArgInFrom、版本不變
指令：`docker compose --env-file .env -f .worktrees/grafana-dockerfile-arg/infra/docker-compose.yaml build --progress plain grafana`

輸出摘要（全文無任何 warning / InvalidDefaultArgInFrom）：
```
#3 [internal] load metadata for docker.io/grafana/grafana-oss:13.0.2
#5 [1/2] FROM docker.io/grafana/grafana-oss:13.0.2@sha256:5dad0df1...
#6 [2/2] RUN mkdir -p /opt/grafana-plugins && grafana cli ... plugins install grafana-clickhouse-datasource 4.23.0 ...
#6 CACHED
#7 naming to docker.io/library/radar-grafana:13.0.2-4.23.0 done
 radar-grafana:13.0.2-4.23.0  Built
```
Grafana 13.0.2、plugin 4.23.0 與 .env.example 一致；plugin 層 CACHED 表示該層 RUN 指令（含 plugin 版本）與修改前完全相同。

## 驗收條件 2：單元測試
`uv run pytest tests/unit/infra -q` -> `3 passed`（真實 Dockerfile、缺預設值被偵測、有預設值被接受）。

## 驗收條件 3：make check
- `pre-commit run --all-files`：trim whitespace / end of files / check yaml / ruff / ruff format / bandit 全 Passed
- `uv run pytest tests/unit -n auto` -> `1117 passed`
- `grep -rn "TODO(grafana-dockerfile-arg)" src tests` 無結果
- PR CI 全綠：qa 未檢查 CI 結果（worker 未 push 時 CI 未跑），本證據不含 CI 狀態，由 PR 流程確認。

## 沒傳 build arg 的行為
- compose 仍有 `GRAFANA_VERSION: ${GRAFANA_VERSION:?...}`，經 compose 建置缺值直接報錯。
- 繞過 compose 直接 docker build 時，預設值 `unset-use-compose-build-arg` 不是存在的 tag，pull 會失敗，不會默默用錯版本（由 tag 不存在推論；沙箱規定只能下 docker compose，未實際執行直接 docker build）。

## 其他檢查
- 寫死設定值：Dockerfile 無寫死版本號、port、token。
- 輕微觀察：測試 regex 只處理單行 `ARG NAME[=...]` 與 `FROM`；多階段或帶引號寫法未涵蓋，現行單階段 Dockerfile 不受影響，不構成 FAIL。

問題數量：0
