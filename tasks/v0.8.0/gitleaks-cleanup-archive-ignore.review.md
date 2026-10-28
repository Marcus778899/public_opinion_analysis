APPROVE eabd633

## 檢查項目

| 項目 | 結果 |
|---|---|
| 負責檔案 | `gh pr view 150 --json files`：只動 `.gitleaksignore`（+2 / -0），未碰 CI workflow 與其他忽略清單 |
| 規則未放寬 | 只加 fingerprint 行，沒有 allowlist、path 或規則層級的放寬 |
| 逐筆是否誤判 | 自行 `git show d452b14:<檔> \| sed -n <行>p`：review.md:9 與 qa.md:17 都是中文敘述，引用 PTT post_id 範例當 `unit_key` 的值，無憑證字串；與檔頭第 3 行說明的既有誤判同類 |
| fingerprint 正確 | commit、路徑、規則 id、行號與上述內容對得上；`git merge-base --is-ancestor d452b14 develop` 成立，commit 已在 develop，squash 本 PR 不影響 |
| 驗收條件 | 回報的 open_questions 逐筆列 fingerprint／內容／理由；gitleaks 8.30.1 本機 0 筆（worker、qa 各跑一次）；`gh pr checks 150`：Check、Security、Integration Test 全 pass |

## 問題

無。

## 建議（非阻擋）

- 這是第三次因封存 review／qa 檔引用誤判字串而補 fingerprint（27610fd → 482309a → d452b14）。之後的 review／qa 證據描述 gitleaks 誤判時，不要原文引用 `key: value` 形式的字串（改寫成「unit_key 的值是 post_id 範例」），封存時就不會再觸發；可由 manager 決定是否寫進注意事項。本結果檔已照此寫法。
