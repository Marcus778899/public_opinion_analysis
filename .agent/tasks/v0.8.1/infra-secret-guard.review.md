APPROVE db577d7

# Review infra-secret-guard 第 2 輪（PR #256，base develop）

範圍：`git diff develop...db577d7`（72493bb 驗收測試、ec68888 實作、db577d7 修正上一輪），5 個檔案；對照 tasks/infra-secret-guard.md（含 2026-10-29 追加）、#254、D-035、開發規格 7.9／7.25、reports/infra-secret-guard.qa.md（PASS db577d7）。

## 上一輪問題

| 問題 | 結果 |
|---|---|
| infra/docker-compose.yaml `secret-check` 用 `env_file: ../.env` 帶進整份 `.env` | 已修：拿掉 env_file，改 `environment:` 只傳四個密碼（`${KEY:-}`，空值交給腳本判定），加 `network_mode: none`。qa 以含 `TELEGRAM_BOT_TOKEN=dummy` 的 env 檔實測，容器內只看得到四個密碼。順帶解決從 worktree 路徑找不到 env_file 的問題 |

## 完整 diff 檢查

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改 infra/docker-compose.yaml（新增 secret-check、三個服務依賴它、PG port 綁 127.0.0.1）、tools/check_secrets.py、tests/unit/tools/test_check_secrets.py、docs/development-spec.md（7.9、7.25 M-4 兩列），皆在「只限」範圍內 |
| 驗收測試 | `tests/unit/acceptance/` 只有 qa 的 72493bb 改過，worker 未動 |
| 禁區 | Kafka、app 服務、e2e compose、scripts/ 未改；沒刪 volume；沒讀 `.env` |
| 條件 1 | secret-check 無 profiles、`restart: "no"`；postgres、clickhouse、grafana 都 `service_completed_successfully`，grafana 保留 clickhouse healthy |
| 條件 2 | `python:3.12-slim` 掛唯讀腳本，不需 build；腳本在無 radar 套件時退回 stderr 輸出，`log.catch` 退成直通，判定邏輯不變 |
| 條件 3 | `127.0.0.1:${POSTGRES_PORT}:5432`；整合測試 compose.yaml、CI 不用 infra compose，e2e compose 不覆寫 postgres ports |
| `init` 行為不變 | `find_bad`／`is_placeholder`／`main` 未改，只多 import 備援 |
| 寫死設定、secret 外洩 | 無寫死 port／密碼；兩條 log 路徑都只印變數名稱；備援路徑的單元測試涵蓋好／壞 env 且斷言不含 `change-me` |
| 文件同步 | 7.9、7.25 M-4 與實作一致（network_mode 屬實作細節，不需寫進文件） |
| TODO | `grep -rn "TODO(infra-secret-guard)" src tests tools`（worktree）無結果 |

上一輪對 qa 兩項觀察（`python:3.12-slim` 寫死、固定 container_name）的判定維持不變。

問題數量：0
