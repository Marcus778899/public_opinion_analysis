# 派工單 otel-api-upgrade

- **類型**：fix
- **負責**：backend
- **通道**：fast
- **目標**：CI Security（osv-scanner）擋下所有 PR：間接相依 `opentelemetry-api` 1.45.1 有漏洞 GHSA-mf5v-w3w3-f6cg（Medium，CVSS 5.3），升到已修版 1.45.2 以上
- **背景**：
  - 由 `fastapi` 0.142.2 帶進來的間接相依，不是新增套件（不需 D-編號）；前例 v0.8.0 authlib、v0.8.1 joserfc 漏洞升級
  - 只升這一個套件的鎖定版本（例 `uv lock --upgrade-package opentelemetry-api`），不連帶升其他套件
  - 若升級需要動 `pyproject.toml` 或帶動其他套件大改，停下回報
- **設計依據**：CLAUDE.md「新增相依套件屬於決策分級②」（本單只升既有間接相依，不新增）
- **相依**：無
- **負責檔案**：
  - `uv.lock`
- **禁區**：不改 `pyproject.toml`、不升其他套件、不改程式碼
- **驗收測試**：無
- **驗收條件**：
  - [ ] `uv.lock` 的 `opentelemetry-api` ≥ 1.45.2，其他套件版本不變（附 `git diff --stat` 與 diff 摘要）
  - [ ] `osv-scanner scan source -r .`（或同 CI 指令）0 個漏洞
  - [ ] 單元測試通過
- **驗證指令**：`uv sync`；`uv run pytest tests/unit -q`；`osv-scanner scan source -r .`；`pre-commit run --all-files`
- **回報檔**：`.agent/reports/otel-api-upgrade.json`

## 執行資訊（ae task 產生）

- Issue：#345
- 分支：`fix/otel-api-upgrade`（從 develop 開出）
- 工作目錄：`.worktrees/otel-api-upgrade`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`

## 追加 2026-11-16

### .agent/reports/otel-api-upgrade.qa.md

FAIL 21fb8d3

## 驗收條件對照

1. uv.lock opentelemetry-api >= 1.45.2、其他套件不變：通過。
   `git diff --stat develop...HEAD`：`uv.lock | 6 +++---`（3 insertions, 3 deletions）。diff 只有 opentelemetry-api 1.45.1 -> 1.45.2 的 version、sdist、wheel；pyproject.toml 與其他檔未動。`uv run --frozen` 實裝版本印出 1.45.2。
2. osv-scanner 0 個漏洞：**未驗證（FAIL）**。本機沒有 osv-scanner；`gh pr checks 346`（run 43817440114）：
   - Security job 失敗，失敗步驟是 `Secrets (gitleaks)`；`Dependencies (osv-scanner)` 與 SAST 皆 skipped，osv-scanner 根本沒跑。
   - Check、Integration Test 查詢時仍 pending。
   這與 develop 已知的 gitleaks 誤判（派工 gitleaks-security-report-fixture）有關；不是本 PR 的 diff 造成（只改 uv.lock），但驗收條件沒有實際驗證到，依規則判 FAIL。
3. 單元測試：通過。`UV_PROJECT_ENVIRONMENT=$TMPDIR/venv uv run --frozen pytest tests/unit -q -x -n 4` -> `2246 passed in 96.89s`。`ruff check .` -> All checks passed。（pre-commit 未重跑，回報稱全 Passed）

## 重現與後續
- 重現：`gh pr checks 346` 看 Security；`gh api repos/Marcus778899/public_opinion_analysis/actions/jobs/133132588882 --jq '.steps[]|[.name,.conclusion]|@tsv'` 顯示 gitleaks failure、osv-scanner skipped。
- 待 gitleaks 誤判修好（gitleaks-security-report-fixture 合併）並讓此 PR 重跑後，Security 的 osv-scanner 步驟實際執行且通過，才能補驗條件 2。程式內容本身沒有發現問題。
- 無其他邊界問題；無寫死設定值（只動 lock 檔）。

- **負責檔案**：`.gitleaks.toml`
- 甲方決定（選項 A）：PR #344（gitleaks 誤判修正）與本單 CI 互卡（#344 被 osv 擋、本單被 gitleaks 擋），把 #344 的修正併進本單一起合併，#344 之後作廢
- 要做的事：把 commit 8d12e3b（分支 chore/gitleaks-security-report-fixture）對 `.gitleaks.toml` 的改動原樣套到本單（例 `git show 8d12e3b -- .gitleaks.toml` 的內容照抄進檔尾，10 行），不做任何修改；不改 `uv.lock` 既有的升級
- 驗證：`gitleaks git --redact --no-banner .` 0 筆；單元測試照常通過；osv-scanner 由 PR 的 CI 驗證
- 若 sandbox 擋 commit：改完驗證完就停，回報 blocked 並附建議 commit 訊息，由甲方代為 commit
