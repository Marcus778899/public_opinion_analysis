APPROVE b9d4a61

PR #93（fix/bot-allowlist-required），對照派工單 `tasks/bot-allowlist-required.md`、D-010、D-009、設計文件 9.2、開發規格 7.21。

## 檢查項目

| 項目 | 結果 |
|---|---|
| D-010：清單沒設／空且 `TELEGRAM_ALLOW_ALL` 非 true 啟動失敗 | `check_allowlist()`（`src/radar/bot/main.py`）在 `main()` 的 `setup_logging` 之後、任何 PG／CH／Kafka／Telegram 連線之前呼叫，丟 `SystemExit`，訊息含兩個變數名 |
| 清單有值只回應清單內（含按鈕） | `handle_update` 未改，訊息與 callback 兩條路徑都經 `is_allowed`；驗收測試以 `handle_update` 實測兩條路徑 |
| `ALLOW_ALL=true` 回應所有人並警告 | 清單空時 `is_allowed` 放行；啟動 `log.warning` 含 `TELEGRAM_ALLOW_ALL` |
| 清單＋ALLOW_ALL 同時設定 | 清單優先＋警告；已寫進開發規格 7.21，與驗收測試一致 |
| D-009：選填寫成註解 | `.env.example` 為 `# TELEGRAM_ALLOW_ALL=false`；`TELEGRAM_ALLOWED_CHAT_IDS` 說明改為必填 |
| 設定只從環境變數讀、無寫死值 | `TelegramSettings.allow_all: bool = False`（安全預設）；bot 容器透過 `env_file: ../.env` 取得新變數，compose 不需改 |
| 文件同步 | 設計 9.2 引用 D-010 與 7.21，細節只寫在 7.21（無重複） |
| 負責檔案 | 變更檔都在負責檔案內；`tests/unit/bot/acceptance/` 未改（`git diff develop -- tests/unit/bot/acceptance` 空）；驗收測試檔為 qa 的 commit 87cf1bf，worker 未改；b9d4a61 只刪掉範圍外的 `tests/unit/acceptance/__init__.py`，收集仍正常 |
| 單元測試 | `check_allowlist` 四種組合、`allow_all` 預設與解析都有測試；舊「空＝不限制」測試已改名改義 |
| e2e 影響 | e2e bot 本來就以空 token 啟動失敗（`infra/docker-compose.e2e.yaml` NOTE），無新影響 |

## 實際執行（worktree，`PYTHONPATH=src uv run --no-sync`）

- `pytest -q tests/unit` → `1027 passed in 3.36s`
- `pytest -q tests/unit/acceptance/bot_allowlist tests/unit/bot/acceptance` → `26 passed in 0.38s`
- `ruff check .` → `All checks passed!`；`ruff format --check .` → `230 files already formatted`
- `grep -rn "TODO(bot-allowlist-required)" src tests` → 無結果

## 非阻擋備註（不需在本 PR 改）

1. `SystemExit` 不會被 `@log.catch`（只抓 `Exception`）記錄，拒絕原因只出現在 stderr（`docker compose logs bot` 看得到），不會進 loggerhelper 的檔案 log。符合驗收條件（容器 log 有說明），若要進檔案 log 可在 raise 前加 `log.critical`，留給之後。
2. `README.md` 第 7 行仍寫「留空代表任何找到這個 bot 的人都能訂閱」，與新行為不符；README 只有 manager 可改，請合併時一起更新（qa 也已提出）。
3. `TELEGRAM_ALLOW_ALL` 以 pydantic bool 解析，`1`／`yes`／`on` 也視為 true；比 D-010 字面寬，但仍需明確設值才開放，不違反 fail closed。
4. 回報檔未直接跑 `make check`（改用等價指令），qa 與本次 review 皆以等價指令獨立驗證通過。
