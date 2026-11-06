PASS 2c1a2e8

# QA 證據：agent-v1-cleanup（PR #273）

驗證 commit：`2c1a2e8`（worktree 乾淨，已併入 develop 含 joserfc 修正）。仲裁 `TEST_WRONG 09d2ffc` 已套用。

## 驗收條件逐條

| 條件 | 結果 | 證據 |
|---|---|---|
| ci.yml 改用 `ae ci`，原步驟保留 | PASS | `git diff develop...HEAD -- .github` 只動：新增 `env.AE`、coverage-gate 前加 Locate／Checkout agent-engineering（token 用 `secrets.AE_TOKEN \|\| github.token`，`persist-credentials: false`）、diff-cover 版本與 `coverage_gate.py` 呼叫換成 `"$AE" ci coverage-gate`、變更偵測 regex 加 `.agent/`。check（make check：ruff、單元測試）、integration（kafka／postgres／clickhouse／grafana、`make coverage` 的 `-n auto` xdist）、security（gitleaks、osv、semgrep、SHA256 驗證、版本與 SHA256 常數）全部沒動 |
| 覆蓋率門檻 80% 沒放寬 | PASS | 工具 `coverage_gate.py` 的 `MIN_PERCENT = 80.0`；`.coverage-exempt` 只刪 `scripts/*`、`templates/*`（目錄已不存在），其餘樣式不變 |
| coverage-gate 用 AE_TOKEN（D-036） | PASS | `gh secret list` 有 `AE_TOKEN`（2026-11-02）；CI log 的 Checkout agent-engineering 步驟成功取得 `Marcus778899/agent-engineering`；pin 的 submodule sha 9077c4a 與 develop 相同 |
| security job 不換 `ae ci security` 的理由 | 成立 | 工具 ci.py 的 `security()` 下載 gitleaks／osv 後直接用，沒有 sha256 驗證（#238 的防護）；PR 事件只掃 `origin/base..HEAD`（現行掃完整歷史，且 D-018／D-026 設定經 `.gitleaks.toml` 照舊生效），換過去會降低防護。ci.yml 已用 NOTE 註明 |
| sync_branch.yml | PASS | 與範本一致，改用 `ae ci sync-branch`（同樣用 AE_TOKEN checkout 工具） |
| 刪除的 scripts/、templates/、contracts/ 沒有專案程式 | PASS | 刪除清單：scripts 12 檔（board、pr、task、release、docs、check_env、coverage_gate、guard_*、init_project、validate_report、_common）、templates 10 檔、contracts/report.schema.json；專案營運程式在 `tools/`（D-006），未動 |
| repo 沒有東西還在執行被刪檔案 | PASS | `grep -rnE "scripts/\|templates/\|contracts/\|coverage_gate\|validate_report\|guard_bash\|guard_paths\|check_env\.py"` 於 Makefile、tools、src、tests、.github、infra、compose*.yaml、Dockerfile、pyproject.toml、.pre-commit-config.yaml、.gitleaks*、.semgrepignore 的命中只有：Makefile:68 註解、pyproject.toml:44 註解、.pre-commit-config.yaml:2 的 exclude 樣式、sync_branch.yml:3 註解（指範本路徑）、test_compose_static.py:259（`not in` 斷言）。全為註解或排除樣式，無執行 |
| `.gitignore` 移除 v1 的 `tasks/`、`reports/` | PASS | diff 確認，`.agent/` 規則未動 |
| 兩個舊驗收測試修改符合仲裁、未削弱防護 | PASS | `git diff develop...HEAD -- tests`：(1) 刪除 `test_check_env_lists_example_passwords_as_required`；同檔 `test_env_example_passwords_use_uppercase_placeholder` 仍斷言四個密碼值正好是 `CHANGE_ME`（改成註解行會 KeyError）；(2) gate 比對字串改 `"coverage-gate"`，`len(cov)==1 and gate`、`if` 含 PR 到 develop 的斷言不動，另加 `assert "coverage-gate" not in joined` 保住 check job 不跑閘門。僅此兩處，與仲裁一致 |
| docs/development-spec.md 同步 | PASS | diff 內 `scripts/coverage_gate.py`、`pr.py`、`check_env.py` 都改成 `ae` 對應寫法 |
| PR 的 CI 全綠 | PASS | 見下 |

## 我自己跑的指令

```
$ cd .worktrees/agent-v1-cleanup && uv run ruff check .
All checks passed!
$ uv run ruff format --check .
326 files already formatted
$ uv run pytest tests/unit -q -n auto
1885 passed in 61.04s (0:01:01)
```

## PR #273 CI（run 41408315062，head 2c1a2e89）

```
$ gh pr checks 273
Check             pass  2m18s  .../actions/runs/41408315062/job/125155312206
Integration Test  pass  3m44s  .../actions/runs/41408315062/job/125155311935
Security          pass  31s    .../actions/runs/41408315062/job/125155312221
```

- Check：`1885 passed in 106.88s`
- Integration Test 的 `Unit and integration tests with coverage`：`2310 passed in 135.26s`
- Locate／Checkout agent-engineering 成功
- 覆蓋率步驟（Coverage of changed lines）輸出：`沒有改到程式碼（只有測試、文件或設定），略過覆蓋率檢查`

## 備註（不構成 FAIL）

1. 本 PR 沒有改到會被量測的程式檔（tests、文件、yml 被排除），所以 CI 上 `ae ci coverage-gate` 只走到「略過」分支；實際 diff-cover 計算與 80% 擋人的路徑尚未在本專案 CI 實跑過。程式邏輯我讀過（`MIN_PERCENT = 80.0`，低於即 `fail`），建議下一張改到 `src/` 的 PR 注意該步驟輸出出現「改到的程式碼覆蓋率 X%」。
2. 負責檔案以外的 v1 殘留文字（`.pre-commit-config.yaml:2` exclude、`pyproject.toml:44` 註解、Makefile:68 註解、README.md、CLAUDE.md、D-006）無執行影響，已在 worker 回報列出，由 manager 另處理。
3. 掃描 `.github` 時 ci.yml 保留 `tasks/`、`reports/` 於變更偵測 regex 是因為驗收測試要求，與條件不衝突。
