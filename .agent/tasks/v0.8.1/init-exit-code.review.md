APPROVE dfee1ba

# init-exit-code review（PR #213）

## 檢查範圍

| 項目 | 結果 |
|---|---|
| 變更內容 | 只有 `tests/unit/acceptance/init-exit-code/test_init_exit_code_acceptance.py`（+342），唯一 commit 是 qa 的 `test(init-exit-code)`，worker 沒改測試 |
| 負責檔案 | 在派工單「驗收測試」目錄內；沒碰程式、compose、其他服務 |
| 寫死設定 | 只有測試用的假網址（`*.invalid`）與假帳密，env 由測試注入，不讀 `.env` |
| 實跑 | 在 worktree 執行 `uv run pytest tests/unit/acceptance/init-exit-code -q` → `18 passed in 7.87s` |
| CI 是否跑到 | 在 `tests/unit/` 底下，`make check` 與 `make coverage` 都會跑；不需要容器 |

## 測試與驗收條件對照

| 驗收條件 | 測試 | 判定 |
|---|---|---|
| 任一步驟失敗 → 結束碼非 0，log 有一行寫出步驟與原因 | topics ×3（admin 失敗、fetch_existing 失敗、topics.yaml 不存在）、clickhouse ×3（500、DDL 中途失敗、migration 檔名錯）、connector ×4（PUT 被拒、task FAILED、Connect 連不上、env 缺） | 有測到：在子行程跑真正的 `main()`，驗證實際結束碼，並要求「同一行」ERROR/CRITICAL log 同時包含步驟與原因字串 |
| 已初始化環境重跑 → 0（冪等） | topics already-exists race、全部已是最新、clickhouse 已 migrate（其他 DDL 回 500 當作防呆）、connector PUT 200/201 | 有測到 |
| 步驟順序不變、失敗就停 | `test_init_command_runs_steps_in_order_failing_fast` 解析 compose `init.command`：順序為 alembic → topics → clickhouse → connector，以 `&&` 串接，不含 `||`、`;` | 有測到，並保護開發規格 7.9 的順序 |

雖然 255 無法重現，這組測試仍然值得合併：它把「失敗 → 非 0 且有 log、冪等重跑 → 0、`&&` 失敗即停」固定成回歸防線。原本沒有任何測試從 `main()` 層級驗證結束碼。

## 非阻擋事項（不需要在本 PR 修）

1. `test_init_exit_code_acceptance.py:54-56,295-300`：`run_tool` 只濾掉 `CONNECT_*`、`CLICKHOUSE_*`，`test_connector_missing_env_var_…` 靠執行環境「剛好沒有」`POSTGRES_*`、`CDC_*`。`make check` 與 CI 都不載入 `.env`，所以目前會過；如果有人用 `uv run --env-file .env pytest` 跑，就會誤判失敗。下次 qa 修改這個目錄時，可以一併把 `POSTGRES_`、`CDC_` 加進過濾清單。
2. 測試會替換工具模組裡的名稱（`AdminClient`、`fetch_existing`、`plan_changes`、`TOPICS_FILE`、`MIGRATIONS_DIR`、`ClickHouseClient`、`httpx2.Client`、`load_connector_spec`），所以跟 `tools/*.py` 的 import 寫法綁在一起。以後重構工具時改了這些名稱，要同步請 qa 更新測試。驗收測試要在子行程驗證結束碼，這樣的代價可以接受。
3. `:285-292` Connect 連不上的情境只要求 log 寫 `not ready`，沒有要求帶出底層錯誤（`connection refused boom`）。這符合工具目前的行為（等到逾時才回報），條件比其他情境寬鬆，但不違反驗收條件。
4. `:339-342` 跟 `:334` 大部分重複（`||`、`;` 已經禁止），沒有壞處。
5. PR 標題是 `fix(...)`、寫的是「成功時結束碼為 0…」，但 PR 沒有任何程式修正。建議 manager 在 PR 描述或合併訊息註明「無程式改動，只加回歸測試；255 無法重現、原因未證實」，避免之後誤以為 #66 已經修好。

## 其他

- 回報（`reports/init-exit-code.json`）已改成「無法重現、原因未證實」，排除項都有證據，跟 qa 第二輪 PASS 一致；不屬於程式碼審查範圍，只確認沒有跟測試矛盾。
