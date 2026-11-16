APPROVE 862e62b

## 檢查範圍

PR #304（`fix/inference-resource-limit`，commit 1cf0dcf、862e62b），對照派工單 `.agent/tasks/inference-resource-limit.md`、`docs/development-spec.md` 7.30 C 與派工順序第 6 列、D-023、D-042。

| 項目 | 結果 |
|---|---|
| 偏離設計 | 無：`inference` 加 `cpus: 2`、`mem_limit: 2g`、`INFERENCE_THREADS: '2'`，與 7.30 C 表格、推論部署段落（spec 882 行）一致 |
| 負責檔案 | 只改 `infra/docker-compose.yaml` 的 `inference` 服務（+4 行）與 qa 的驗收測試；`inference-shadow`（`cpus: 2`、`mem_limit: 1.5g`、threads `'2'`）與其他服務未動 |
| 寫死設定 | 資源上限為規格指定的字面值，同 shadow 寫法（D-023），不屬 port／網址／token；`.env.example` 的選填 `# INFERENCE_THREADS=2` 已存在，服務定義覆寫它與 shadow 一致 |
| 設定生效 | `src/radar/ml/inference/main.py:221` 以 `settings.threads` 傳入 classifier，env 名稱對得上 |
| bug／安全 | 無；註解符合 NOTE 慣例長度 |
| 測試 | 驗收測試 6 項涵蓋三個驗收值、threads 為字串、role 仍 primary、shadow 不變；worktree 內 `PYTHONPATH=$(pwd)/src .venv/bin/python -m pytest tests/unit/acceptance/inference-resource-limit -q` → 6 passed |
| compose 合法性 | qa 已跑 `docker compose ... config --quiet` exit 0（worker 回報的 open_question 已由 qa 補跑） |
| CI | review 時 Security pass，Check、Integration Test 仍 pending；merge 由 `ae pr merge` 檢查 CI |

問題數量：0
