APPROVE 2796fa2

# Review：secret-placeholder-guard（PR #253，對 develop 完整 diff）

## 檢查項目

| 項目 | 結果 |
|---|---|
| 改動範圍 | 6 檔，全在負責檔案內：`.env.example` 只改四個密碼行；`infra/docker-compose.yaml` 只改 `init` 的 command 與其上一行註解；`docs/development-spec.md` 只改 7.9 執行順序（init 順序說明）與 7.25 威脅表新增 M-4 列；`tools/check_secrets.py`、`tests/unit/tools/test_check_secrets.py` 新檔；驗收測試目錄只有 qa 的 `92db2ae test(...)`，worker 沒碰 |
| 禁區 | 沒改 `scripts/`、其他服務的 compose；程式只讀 `os.environ`，不讀 `.env` |
| 驗收條件 1 | `is_placeholder`：`None`／空白／`strip().lower()` ∈ {change-me, changeme, change_me} → True；log 只印變數名稱（`", ".join(bad)`），`sys.exit(1)`。含子字串的值（`my-change-me-pass-77`）不誤判 |
| 驗收條件 2 | 全部是其他值 → 只印數量，正常結束（rc 0） |
| 驗收條件 3 | `python tools/check_secrets.py && alembic ...`，`&&` 串接；`init` 有 `env_file: ../.env`，四個變數都進得到容器；Dockerfile 已 `COPY tools/` |
| 驗收條件 4 | `.env.example` 四行改 `CHANGE_ME`，驗收測試以 `check_env.parse` 確認列為必填 |
| 入口規範 | `main()` 第一行 `setup_logging`、`@log.catch(level="CRITICAL")`；`log.catch` 不攔 `SystemExit`，失敗路徑結束碼維持 1 |
| 寫死設定 | 無；變數名稱清單屬程式邏輯，不是設定值 |
| 其他使用 `.env.example` 的地方 | CI 兩個 job 都 `cp .env.example .env`：check job 只跑 `make check`；integration job 用根目錄 `compose.yaml`（密碼寫死 `it`），不跑 `init`，不受影響。repo 內沒有其他程式依賴 `change-me` 這個值 |
| 文件同步 | 7.9 執行順序與 7.25 威脅表已更新；README 第 1 步「不可用 `change-me`」仍正確 |
| 測試 | 驗收測試用 subprocess 實跑腳本，涵蓋 4 變數 × 5 種大小寫寫法、空值、未設定、多個同時錯、成功與失敗都不印值、init 順序與 `&&`；單元測試涵蓋 `is_placeholder` 邊界、`find_bad` 順序、`main` 成功與失敗。PR checks（Check、Integration Test、Security）全綠，tools/* 依 `.coverage-exempt` 不量覆蓋率 |

## 非阻擋意見

- `tests/unit/tools/test_check_secrets.py::test_main_bad_env_exits_nonzero_without_printing_value` 用 capsys 斷言「不印值」：loggerhelper 的 sink 不一定寫進 capsys 攔到的 stream，這條斷言可能空轉。不阻擋，因為驗收測試以 subprocess 實際檢查 stdout＋stderr，同一條件已確實測到。

## qa 觀察 1：預設 profile 的 postgres、clickhouse、grafana 不經 init 就啟動 —— 建議另開 backlog，不擋本 PR

理由：

1. **本單範圍已達成**：派工單只規定 `init` 先檢查；資安 v0.7.0 M-4 的對策建議本來就是「`.env.example` 改成 `CHANGE_ME` 讓 `check_env.py` 擋」，本 PR 做到了，另外加上 init 這道。#119 可以隨本 PR 關閉。
2. **但仍有實際殘留風險，不能只當備註**：`make up`（只有基礎設施，不帶 app profile）時三個服務會用 `.env` 裡的值啟動，而 M-4 要保護的資產正是 Grafana admin 與 ClickHouse 帳號。擋住這條路的只剩 README 第 1 步的 `check_env.py`，是人工步驟，沒有強制。
3. **postgres 讓殘留風險更大**：`infra/docker-compose.yaml:108` 是 `"${POSTGRES_PORT}:5432"`，沒有綁 `127.0.0.1`（clickhouse、grafana 等都綁本機），所以 PG 用公開的範例密碼時，同一個網段就連得到，不只是 M-4 說的 DNS rebinding。這是本 PR 之前就有的狀況，目前沒有 issue 追蹤。
4. **做法是可逆的 compose 調整，不是本單能順手改的**：例如在預設 profile 加一個一次性的 `secrets-check` 服務（同一支 `tools/check_secrets.py`），讓 postgres、clickhouse、grafana `depends_on: service_completed_successfully`；PG port 改成 `127.0.0.1:${POSTGRES_PORT}:5432`（要先確認本機工具與 e2e 沒有從其他介面連）。compose 是受保護路徑，又改到其他服務的設定，屬本單禁區，所以要另開單。
5. **排進哪一輪屬決策分級①**：BOARD 本輪範圍是列舉的兩批 issue，要不要加進本輪由 manager／甲方決定；開 backlog issue 本身不需要 D-編號。建議 issue 一併列兩點：(a) 預設 profile 服務的密碼檢查；(b) PG port 只綁本機。發版前 security 也應把 M-4 標為「部分修正」而不是「已修正」。

## qa 觀察 2：既有開發環境 init 會失敗 —— 符合預期（fail closed），但需要告知甲方

- 這是本單的目的，不算缺陷。
- 甲方的開發 `.env` 若仍是 `change-me`，下次 `up-app`／`e2e-up` 會停在 init。改 `.env` 時要注意：`POSTGRES_PASSWORD` 與 Grafana 的 `GF_SECURITY_ADMIN_PASSWORD` 只在 volume 第一次初始化時生效，既有 volume 不會跟著換（資安 v0.7.0 M-4 對策第 2 點已提過）；PG 要用 `ALTER USER` 改密碼，或 `down -v` 重建（刪資料，屬決策分級④）；Grafana 用 `grafana cli admin reset-admin-password`。ClickHouse 帳號每次啟動從環境變數讀，改 `.env` 後重啟即可。
- 建議 manager 合併後通知甲方，並把「改密碼的步驟」放進觀察 1 的 backlog 或 README（README 歸 manager）。

## 問題數量：0（阻擋）；非阻擋 1；建議另開 backlog 1
