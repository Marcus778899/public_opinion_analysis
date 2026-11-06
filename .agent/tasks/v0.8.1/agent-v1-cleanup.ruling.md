TEST_WRONG 09d2ffc

# 仲裁：agent-v1-cleanup 的 disputes

依據：派工單 `.agent/tasks/agent-v1-cleanup.md`（目前的契約：刪除根目錄 `scripts/`、ci.yml 照範本改用 `ae ci coverage-gate`）；worker 回報 `.agent/reports/agent-v1-cleanup.json` 的 disputes。

## 測試檔來源檢查

- 本單沒有自己的驗收測試目錄；爭議的兩個測試是舊單的鎖定驗收測試，最後由 qa 的 `test(...)` commit 寫入（92db2ae `test(secret-placeholder-guard)`、0e7c370 `test(test-infra-compose)`／8b1488f）
- 本分支（afe02cc 之後的 8b5a38c、09d2ffc）沒有改到 `tests/`，worker 沒碰測試
- 兩個測試在當時的契約下是對的；失敗是因為本單的契約明確要求移除它們依賴的 v1 檔案與字串，不是實作做錯

## 逐條判定

| 測試 | 契約條文 | 判定與理由 |
|---|---|---|
| `tests/unit/acceptance/secret-placeholder-guard/test_secret_placeholder_guard.py::test_check_env_lists_example_passwords_as_required` | 本單驗收條件「根目錄 `scripts/` 刪除」；原單 secret-placeholder-guard 驗收條件「`.env.example` 的範例值改成 `CHANGE_ME`，`check_env.py` 就會把它們列成必填」 | **TEST_WRONG**。測試 import `scripts/check_env.py`，跟本單要求刪掉 `scripts/` 直接衝突，實作改不了。v3 工具版 `.claude/skills/agent-engineering/lib/agent_engineering/check_env.py` 的 `parse()` 規則相同（`PLACEHOLDER = "CHANGE_ME"`，`KEY=值` 行列入、`# KEY=` 註解行不列入），但 CI 的 check job 沒有 checkout 工具（submodule 只在 integration job 的閘門步驟才取），worktree 也用 sparse-checkout 排除 `.claude/`（D-013），所以不能改成 import 工具版 |
| `tests/unit/acceptance/test_infra/test_compose_static.py::test_ci_integration_job_runs_coverage_and_gate_only_for_pr_to_develop` | 本單驗收條件「ci.yml 照範本改用 `ae ci`（coverage-gate）」；不可放寬覆蓋率門檻 | **TEST_WRONG**。測試用字串 `coverage_gate.py` 找閘門步驟，本單要求改成 `"$AE" ci coverage-gate`，字串必然消失。測試要防的事（閘門存在、只在 PR 到 develop 時跑、`make coverage` 只跑一次）現行 ci.yml 都符合：`Coverage of changed lines` 步驟的 `if` 含 `github.event_name == 'pull_request' && github.base_ref == 'develop'` |

## 測試應該怎麼改（由 qa 改）

1. `test_check_env_lists_example_passwords_as_required`：**刪除**。
   - 原本要防的事：`.env.example` 這四個密碼的範例值被列成甲方必填。同檔的 `test_env_example_passwords_use_uppercase_placeholder` 已保住它：值必須正好是 `CHANGE_ME`（工具判定必填的字樣），而且該行若被改成註解 `# KEY=`，`lines[name]` 會 KeyError 失敗，等於也驗了「不是選填」。
   - 不要改成 import 工具版 check_env（理由見上表，CI check job 會找不到）。
2. `test_ci_integration_job_runs_coverage_and_gate_only_for_pr_to_develop`：第 265 行比對字串 `"coverage_gate.py"` 改成 `"coverage-gate"`，其他斷言不動。
   - 用 `_step_text`（整個 step 的 JSON）比對時，現行 ci.yml 只有 `Coverage of changed lines` 一步會命中（`Set up Python for coverage gate` 是空白不是連字號），`if` 條件斷言照樣檢查到閘門只在 PR 到 develop 時跑；`len(cov) == 1` 照樣保住 `make coverage` 只跑一次。
   - 順帶（非失敗項，建議同一次改）：第 259 行 `test_ci_check_job_only_runs_make_check` 的 `assert "coverage_gate" not in joined` 改名後會永遠成立而失去作用，加一行 `assert "coverage-gate" not in joined`，保住「check job 不跑閘門」。

## qa 項目

本次仲裁由 worker 的 disputes 觸發，不是 qa FAIL，沒有 qa 證據檔要判。

## 契約問題

- 舊單 secret-placeholder-guard 的驗收條件寫死 `check_env.py`（v1 路徑）；本單刪除後該條件改由 `test_env_example_passwords_use_uppercase_placeholder` 涵蓋，不需開 D-編號（不降低防護，可逆）
- worker 的 open_questions 列的負責檔案以外 v1 殘留（README.md、CLAUDE.md、docs/decisions.md D-006、`.pre-commit-config.yaml`、`pyproject.toml`、Makefile 註解）由 manager 另行處理，不影響本判定
