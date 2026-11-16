PASS 0f86c7a

## 驗收條件
- 兩個工具 checkout 步驟位置：ci.yml 內順序為 Detect code changes(git diff) -> Locate/Checkout agent-engineering -> Use Docker Hub mirror -> Prepare env -> Pull images（第一個 docker compose）-> Install uv -> uv sync -> make coverage；if 條件與原本逐字相同（diff 只是搬移）。OK
- Checkout 有 `persist-credentials: false`。OK
- Makefile 無 `check_env`（grep 無結果），setup 註解改為 `ae check-env setup`。OK
- 驗收測試：`PYTHONPATH=$(pwd)/src ../../.venv/bin/python -m pytest tests/unit/acceptance/ci-token-order -q` -> 9 passed
- tests/unit 全跑（含 7.26 test_ci_integration_first_step_diffs_changed_files）：1989 passed
- ruff check：All checks passed；ruff format --check：333 files already formatted
- PR #301 CI（run 41797628936）：Check pass 2m25s、Integration Test pass 3m33s、Security pass 25s

## open_questions（checkout 進 .claude/skills 會不會被掃到）
- pyproject `[tool.ruff] extend-exclude = ["docs", ".claude"]`；且 integration job 不跑 ruff／pre-commit（只在 check job，該 job 無工具 checkout）
- `make coverage` 只跑 `pytest tests/unit tests/integration --cov=src/radar`，不走訪 .claude
- CI 實跑 Integration Test 綠燈，含 Coverage of changed lines 步驟。結論：不會掃到

## 其他
- 寫死設定值：diff 內無新增 port／網址／token，token 仍走 secrets.AE_TOKEN
- 未做：沒有實際用 `AE_TOKEN` 私有 repo 驗 checkout（CI 用 fallback github.token 通過）

問題數量：0
