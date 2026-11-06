APPROVE 2c1a2e8

# Review：PR #273 agent-v1-cleanup

對照：派工單（含 2026-11-02 追加）、仲裁 `agent-v1-cleanup.ruling.md`、worker 回報、qa 證據、工具範本 `.claude/skills/agent-engineering/templates/project/{ci,sync_branch}.yml`、`lib/agent_engineering/ci.py`。

## 檢查項目

| 項目 | 結果 |
|---|---|
| 只改負責檔案 | 是。變更檔：`.coverage-exempt`、`.github/workflows/{ci,sync_branch}.yml`、`.gitignore`、`docs/development-spec.md`、刪除 `scripts/`（12 檔）、`templates/`（10 檔）、`contracts/`（1 檔）、追加範圍的兩個驗收測試。禁區（`.claude/`、`CLAUDE.md`、`.agent/`、`src/`）沒動 |
| 測試檔來源 | 兩個測試檔只有 qa 的 `603437f test(agent-v1-cleanup)` 改；worker 的 8b5a38c、09d2ffc 沒碰 `tests/`。修改內容與仲裁一致：刪 `test_check_env_lists_example_passwords_as_required`；比對字串改 `coverage-gate`；check job 加 `assert "coverage-gate" not in joined` |
| ci.yml 原步驟保留 | 是。check（make check：ruff、單元測試）、integration（kafka／postgres／clickhouse／grafana、`make coverage` 含 xdist）、security（gitleaks＋`.gitleaks.toml` 的 D-018／D-026、osv、semgrep、SHA256 驗證）未刪；security 只改註解 |
| 覆蓋率門檻 | 未放寬：`ae ci coverage-gate` 跑工具的 `coverage_gate.py`（`MIN_PERCENT = 80.0`），比對 `origin/<base_branch>`，diff-cover 版本 10.6.0 與原本相同；`if` 仍限 PR 到 develop 且有改程式；`COVERAGE_SRC_ROOTS` 保留；integration job checkout 仍 `fetch-depth: 0` |
| 工具 checkout 安全性 | 照範本：`persist-credentials: false`、`AE_TOKEN \|\| github.token`、ref 釘 submodule sha；放在跑專案測試之後，測試／lint 不會掃到工具 |
| 不換 `ae ci security` | 理由成立：工具版不驗下載檔 SHA256（#238）、PR 只掃新增 commit，換過去降低防護；ci.yml 已以 NOTE 註明 |
| sync_branch.yml | 與範本只差名稱、註解與佔位符（main／develop）；`ae ci sync-branch` 邏輯與原本 inline 腳本等價（含被搶先 push 時的判定） |
| 變更偵測 regex 加 `.agent/` | 只改 `.agent/`（布告欄、派工單、回報）時略過整合測試，與原本略過 `tasks/`、`reports/` 同性質；check、security 仍照跑，可接受 |
| `.gitignore` | 移除 `tasks/`、`reports/`，`.worktrees/` 等保留；主目錄目前沒有 `tasks/`、`reports/` 目錄，不會冒出未追蹤檔 |
| 文件同步 | `docs/development-spec.md` 四處 v1 寫法改成 `ae`；`grep -rn "scripts/" .github .coverage-exempt docs/development-spec.md` 無結果 |
| 寫死設定值、secret | 無 |
| CI | run 41408315062（head 2c1a2e89）Check／Integration Test／Security 全 pass |

## 備註（不擋合併）

1. 本 PR 沒改到受量測的程式，CI 上 coverage-gate 只走到「略過」分支；sync-branch 只在 push main 時跑，發版前未實跑。發版後確認 Sync workflow 成功，下一張改 `src/` 的 PR 確認出現「改到的程式碼覆蓋率 X%」。
2. 負責檔案外的 v1 殘留文字（README.md:7、118，CLAUDE.md:32，D-006 文字，`.pre-commit-config.yaml:2`、`pyproject.toml:44-45` 的排除樣式，Makefile:68 註解）由 manager 另行處理（worker 回報已列）。
