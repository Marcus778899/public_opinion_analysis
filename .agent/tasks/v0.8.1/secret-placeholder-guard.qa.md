PASS 2796fa2

# QA 證據：secret-placeholder-guard（PR #253）

驗證環境：`.worktrees/secret-placeholder-guard`，`PYTHONPATH=$PWD/src`，HEAD 2796fa2。以下皆為本人實際執行。

## 驗收條件

1. 空值／change-me／changeme／change_me（不分大小寫）失敗：PASS
   - 以 `env -i` 設定其中一個密碼為下列值，其餘三個為 `Sup3rSecretXYZ`，執行 `python tools/check_secrets.py`：
     `""`、`change-me`、`ChangeMe`、`CHANGE_ME`、`change_me`、`"  "`（純空白）→ 全部 rc=1，
     輸出 `these variables are empty or still the example value: POSTGRES_PASSWORD`。
   - 四個全未設定 → rc=1，列出四個變數名稱。
   - 輸出中搜尋 `Sup3rSecret`：0 筆（不印值）。
2. 四個皆為其他值（a1、b2、c3、d4）→ rc=0，輸出 `all 4 secrets are set`：PASS
3. `init` 先跑檢查：PASS
   - 展開後（用 `docker compose ... --profile app config --format json`，只取 init）：
     `['sh','-c','python tools/check_secrets.py && alembic upgrade head && python tools/create_topics.py && python tools/migrate_clickhouse.py && python tools/register_connector.py']`
     檢查在最前，以 `&&` 串接，失敗就不做後面。
   - 依賴：api、cdc-watchdog、crawler、ingest、scheduler 的 `depends_on.init` 皆為 `service_completed_successfully`；
     inference、inference-shadow、heat、bot、label-stream 以 `<<: *app` 繼承同一條 `depends_on`，且無覆寫。
     init 失敗（非 0）後這些服務不會啟動。
   - Dockerfile 有 `COPY tools/ tools/`，image 內有 check_secrets.py。
4. `.env.example` 四個密碼改成 `CHANGE_ME`（diff 確認，只動這四行）：PASS
5. 測試與 make check：PASS
   - `uv run pytest tests/unit/acceptance/secret-placeholder-guard tests/unit/tools` → `57 passed in 3.07s`
   - `pre-commit run --all-files` → 全部 Passed（ruff、ruff format、bandit、check yaml…）
   - `uv run pytest tests/unit -q` → `1770 passed in 75.22s`
   - `grep -rn "TODO(secret-placeholder-guard)" src tests tools` → 無結果

## 不印密碼值（所有輸出路徑）

- 失敗路徑只輸出變數名稱（上述 6 種值＋全未設定，輸出皆不含密碼值）。
- 成功路徑只印數量。程式沒有 print、沒有輸出任何 value；`log.catch` 只包 SystemExit 以外的例外，
  正常失敗走 `log.error` + `sys.exit(1)`。
- compose 檢查：未把整份 config 貼入；為避免讀真實 `.env`，用 worktree 的 `infra/` 副本加 `.env.example` 內容
  （皆為 CHANGE_ME，非機密）於 scratchpad 展開，只摘錄 init 的 command 與 depends_on。

## 觀察（不列為 FAIL，超出本單驗收條件）

- postgres、clickhouse、grafana 在預設 profile，不依賴 init，`.env` 仍是範例值時仍會啟動（Grafana 以 CHANGE_ME 為管理密碼）。
  本單只規定 `init` 先檢查；若要連這些也擋需另開單。
- worker 回報已提到：既有開發環境 `.env` 若仍為 change-me，下次 up-app 的 init 會失敗，且既有 PG volume 的密碼不會隨 .env 改變。
- 真實 `.env` 未讀（規定）；`docker compose --env-file .env config` 直接對 worktree 路徑會因 worktree 無 `../.env` 失敗，屬環境因素，不是 PR 問題。

## 問題數量：0
