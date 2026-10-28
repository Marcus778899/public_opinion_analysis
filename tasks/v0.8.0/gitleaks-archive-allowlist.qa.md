PASS 629b2ef

# 驗證 gitleaks-archive-allowlist（PR #153）

gitleaks 8.30.1（darwin_arm64，照 CI 方式從 GitHub release 下載到 $TMPDIR）。以分支 clone 到 $TMPDIR 驗證；git 模式掃歷史，所以改設定檔不需重新 commit。

## 1. 分支 0 筆，且不靠 tasks/ 的 fingerprint 也是 0 筆
`gitleaks git --redact --no-banner .`：228 commits scanned，no leaks found（exit 0）。

| 情境（clone 的 629b2ef） | 發現數 |
|---|---|
| A 設定檔＋分支的 .gitleaksignore | 0 |
| B 設定檔＋完全沒有 .gitleaksignore | 9（全是非 tasks/ 的既有項目：docker-compose 3、settings.py、development-spec、design、security/v0.6.0、uat/v0.7.0、.gitleaksignore 本身；這些仍由保留的 fingerprint 壓住） |
| C 無設定檔＋無 .gitleaksignore | 16 |
| D 無設定檔＋分支的 .gitleaksignore | 7（正好是被刪掉的 7 筆 tasks/ 項目） |

C 減 B = 7 筆，路徑全在 tasks/（v0.6.0 ci-gitleaks-ignore 3、v0.7.0 gitleaks-archive-ignore 2、backlog-cleanup-2026-10 2）。設定檔除 tasks/ 外沒有少抓任何既有發現。

## 2. 反向測試（tasks/ 以外仍抓得到）
暫時 repo 在 src/、tasks/、docs/tasks/、nottasks/ 各放三種假憑證（隨機組成的 AWS access key、generic 形式、GitHub PAT 形式，不含 EXAMPLE 等停用字）。

- 套用本分支 .gitleaks.toml：9 筆，src/、docs/tasks/、nottasks/ 三個目錄 × aws-access-token／generic-api-key／github-pat 各 1，tasks/ 0 筆
- 不套設定檔：12 筆，多出的 3 筆正是 tasks/ 的三種
- 結論：只排除開頭為 tasks/ 的路徑（錨定，docs/tasks/ 與 nottasks/ 不受影響），三種預設規則都仍生效
- 規則數量：.gitleaks.toml 為 `[extend] useDefault = true` 加一個 allowlists（paths），沒有任何 `[[rules]]`（grep 計數 0），所以不改動、不新增、不刪除規則。gitleaks 無列出規則指令，以此結構證明

### worker 的 AWS 格式假字串沒被抓到的原因
預設 allowlist／規則會略過範例值與低熵值。對照實驗：AWS 官方文件範例金鑰（結尾 EXAMPLE）→ 0 筆；全相同字元的 AKIA 字串 → 0 筆；隨機組成的 AKIA 字串 → 抓到 1 筆（aws-access-token）。所以是 worker 挑的值被略過，不是設定檔造成；與設定檔無關。

## 3. 刪除的 .gitleaksignore 項目
diff 刪 7 行，路徑全為 tasks/v0.6.0、tasks/v0.7.0、tasks/backlog-cleanup-2026-10 底下；保留的 6 行為非 tasks/ 項目（docker-compose、settings.py、development-spec、security、uat、.gitleaksignore 本身）。另新增一行檔頭註解說明。無多刪。

## 4. 其他驗收條件
- 回報（reports/gitleaks-archive-allowlist.json）與 PR 說明沒有引用 key: value 形式的字串（人工檢視，並用 regex 掃 PR 說明 0 筆）
- PR #153 CI：Check SUCCESS、Integration Test SUCCESS、Security SUCCESS（gh pr view 153，已全部 COMPLETED）
- 禁區：變更檔只有 .gitleaks.toml、.gitleaksignore；沒動 CI workflow、版本

## 問題
無。備註：回報 open_questions 說 CI 尚待確認，現已確認全綠。
