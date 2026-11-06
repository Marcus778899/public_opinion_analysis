APPROVE c75a063

## 檢查結果

| 項目 | 結果 | 依據 |
|---|---|---|
| 負責檔案範圍 | 符合 | 只改 `Makefile`、`tests/unit/test_makefile_up_hint.py`（`git diff --stat origin/develop...HEAD`） |
| 禁區 | 符合 | compose、健康檢查、其他 target、`.PHONY`、文件都沒動；Makefile 只改 `up` 的 `##` 說明一行 |
| 條件 1：說明機制看得到限制與替代指令 | 符合 | Makefile 沒有 `help` target，既有機制就是 target 行的 `##`；內容含只起基礎設施、connect unhealthy、`--wait` 回非 0、`make up-app` |
| 條件 2：`up` 實際指令不變 | 符合 | recipe 仍是 `$(COMPOSE) up -d --wait`，`stop-e2e` 相依也沒變 |
| 條件 3：單元測試防止提示被改掉 | 符合 | 見下方變異測試 |
| 條件 4：`make check` | worker 回報通過；CI 待確認 | worker：2023 passed。review 當下 CI 的 Security 已過，Check 與 Integration Test 仍在跑，由 `ae pr merge` 把關 |
| 與開發規格 7.30 B 一致 | 符合 | 已知限制的敘述相符 |
| `make up-app` 確實能解決 | 符合 | `infra/docker-compose.yaml` 的 `init` 是 `profiles: ["app"]`，並執行 `tools/register_connector.py`；`up-app` 帶 `--profile app` |
| 寫死設定值、bug、安全問題 | 無 | 只改說明文字；測試只讀 repo 內的 Makefile |

## 實際執行的驗證

- `uv run pytest tests/unit/test_makefile_up_hint.py -v`：2 passed
- `uv run ruff check`、`uv run ruff format --check`（該測試檔）：通過
- 變異測試（在 `$TMPDIR` 的 Makefile 副本上，做完已刪除）：
  - `up` 說明改回「啟動基礎設施」：`test_up_說明_提到_connect_unhealthy_與_up_app` FAILED，另一個 passed
  - recipe 改成 `$(COMPOSE) --profile app up -d --wait`：`test_up_實際指令_維持只起基礎設施並等待` FAILED，另一個 passed

## 不擋合併的觀察

- `tests/unit/test_makefile_up_hint.py:14`、`:22` — 測試函式名稱含中文，develop 的 `tests/` 目前沒有其他這樣的例子，與 CLAUDE.md「程式碼識別字用英文」不一致；ruff 沒開對應規則（`select` 不含 `PLC`）所以 lint 抓不到。屬命名風格，不影響驗收，要統一可排 backlog。
- `Makefile:10` — 說明寫「沒有 init 時」，7.30 B 寫的是「全新環境」。connector 註冊過的環境跑 `make up` 不受影響，只看這句可能以為每次都會失敗；句中已引用 7.30 B，且符合派工單目標的寫法，不要求修改。

沒有 REQUEST_CHANGES 項目。
