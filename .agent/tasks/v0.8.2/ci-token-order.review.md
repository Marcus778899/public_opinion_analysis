APPROVE 0f86c7a

## 檢查範圍

- `gh pr diff 301`（head 0f86c7a）對照派工單 `.agent/tasks/ci-token-order.md`、開發規格 7.30 F（#276、#277）、派工順序第 7 列、威脅表 `AE_TOKEN` 列

## 結果

| 項目 | 判定 |
|---|---|
| 偏離設計 | 無。「Locate agent-engineering」「Checkout agent-engineering」整段搬到「Detect code changes」之後、「Use Docker Hub mirror」之前；搬到新位置前只有 Checkout 與 git diff 兩步，沒有跑 PR 的程式、相依或 compose（符合 7.30 F #277、威脅表 `AE_TOKEN` 對策） |
| `if` 條件 | 兩步逐字不變；coverage gate 兩步（Set up Python、Coverage of changed lines）留在 `make coverage` 之後原位 |
| `persist-credentials: false` | 保留；token 仍走 `secrets.AE_TOKEN \|\| github.token`，沒有寫死值 |
| 註解 | 原本「放在跑測試的步驟之後才 checkout：測試、lint 不會掃到工具本體」已改成新的理由，沒有留下與現況矛盾的註解 |
| 工具檔提前出現在磁碟上的影響 | ruff `extend-exclude` 含 `.claude`；integration job 不跑 lint；`make coverage` 只收 `tests/unit tests/integration`、`--cov=src/radar`；`uv sync` 不碰 `.claude`。不影響測試與覆蓋率，CI 實跑也綠燈 |
| Makefile（#276） | `setup` 註解改 `ae check-env setup`；檔內已無 `check_env.py` |
| 負責檔案 | worker 只改 `.github/workflows/ci.yml`、`Makefile`；`tests/unit/acceptance/ci-token-order/` 是 qa 的驗收測試；`.gitleaks.toml` 與其他 job 未動 |
| 測試是否測到驗收條件 | 9 個測試以 yaml 解析 integration job：順序（在 git diff 後、在任何 docker compose／uv／make／setup-uv 前）、`if` 條件逐字比對、`persist-credentials is False`、coverage gate 仍在測試後、Makefile 兩項。涵蓋四條驗收條件 |
| bug／安全 | 無新問題。第一個 Checkout 用預設 `persist-credentials`（留 `github.token` 在 `.git/config`）是既有行為、不在本單範圍 |

## 實際執行

- `git -C .worktrees/ci-token-order rev-parse --short HEAD` → `0f86c7a`（與 PR head 一致），工作樹乾淨
- `PYTHONPATH=$(pwd)/src ../../.venv/bin/python -m pytest tests/unit/acceptance -q -k "ci_token or ci_integration_first_step"` → `10 passed`（含 7.26 的 `test_ci_integration_first_step_diffs_changed_files`）
- `gh pr checks 301` → Check pass、Integration Test pass、Security pass（run 41797628936）

問題數量：0
