PASS db577d7

# QA infra-secret-guard（PR #256，commit db577d7）

方法：compose 與 tools/check_secrets.py 複製到 scratchpad（`.../scratchpad/sg/`），env 檔用 `.env.example` 副本（另一份把四個密碼換成真值、兩份都加 `TELEGRAM_BOT_TOKEN=dummy`），project 名 `sgqa`；未對真實 infra compose 下 up，未讀真實 `.env`。

## 驗收條件

| 條件 | 結果 | 證據 |
|---|---|---|
| 預設 profile 有一次性檢查服務；postgres／clickhouse／grafana 以 service_completed_successfully 依賴；失敗時不啟動 | OK | `config --format json`：secret-check 無 profiles、restart "no"；postgres、clickhouse、grafana 的 depends_on 都有 `secret-check: service_completed_successfully`（grafana 另保留 clickhouse healthy）。範例值跑 secret-check 結束碼 1（下）。未實跑 up（依規定），失敗即擋靠 compose 語意 |
| 不需 build radar-app；不拖慢 make up | OK | image `python:3.12-slim` 掛唯讀腳本，`run --no-deps` 直接跑成功 |
| postgres 綁 127.0.0.1 | OK | config 輸出 postgres ports：host_ip 127.0.0.1, 5432→5432；compose.yaml／compose.ci.yaml 未改（diff 只動 5 個檔） |
| 開發規格同步；驗收測試與 make check；無 TODO | OK | 見下 |

## 指令與輸出

範例值（`run --rm --no-deps secret-check`，exit 1）：
```
ERROR check-secrets these variables are empty or still the example value: POSTGRES_PASSWORD, CLICKHOUSE_PASSWORD, CLICKHOUSE_GRAFANA_PASSWORD, GRAFANA_ADMIN_PASSWORD
```
正常值（exit 0）：
```
INFO check-secrets all 4 secrets are set
```
環境隔離（env 檔含 TELEGRAM_BOT_TOKEN=dummy，容器內以 `--entrypoint python` 檢查）：
```
['CLICKHOUSE_GRAFANA_PASSWORD', 'CLICKHOUSE_PASSWORD', 'GRAFANA_ADMIN_PASSWORD', 'POSTGRES_PASSWORD']
TG None
```
網路隔離（同法）：網卡只有 lo 與未啟用的虛擬介面（tunl0 等），`socket.create_connection(('1.1.1.1',53))`：
```
NET FAIL [Errno 101] Network is unreachable
```
測試與 lint（在 worktree）：
- `uv run pytest tests/unit/acceptance/infra-secret-guard tests/unit/tools -q`：49 passed
- `uv run pytest tests/unit -q`：1816 passed
- `uv run ruff check .`：All checks passed；`ruff format --check .`：324 files already formatted
- `pre-commit run --all-files`：全部 Passed（trailing whitespace、end of files、check yaml、ruff、ruff format、bandit）
- `grep -rn "TODO(infra-secret-guard)" src tests tools`：無結果

## 邊界與寫死值
- 空值：`${KEY:-}` 讓缺變數時傳空字串，由腳本判定並只印變數名稱（輸出已確認不印密碼值）。
- 新增內容無寫死的 port／token；`127.0.0.1` 為綁定位址，非設定值。
- 前次 review 的 env_file 相對路徑問題已消失（secret-check 已無 env_file）。

## 問題
無。
