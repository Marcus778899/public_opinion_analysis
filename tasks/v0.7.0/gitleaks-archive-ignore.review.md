APPROVE 1e1e5f3

# Review：gitleaks-archive-ignore（PR #89，受保護路徑 `.gitleaksignore`）

| 檢查項 | 結果 |
|---|---|
| 範圍 | `gh pr diff 89` 與 `git diff --name-only develop...HEAD` 只有 `.gitleaksignore`（+4 −1）；1 個 commit `1e1e5f3`，訊息格式正確 |
| 只加必要的 fingerprint | 新增 3 行，都是 `27610fd…:tasks/v0.6.0/ci-gitleaks-ignore{.qa.md:14,.md:6,.review.md:9}`，精確到 commit＋檔案＋行號；沒有路徑萬用、沒有整檔或整條規則的忽略 |
| 逐筆確認是誤判 | 自己用 `git show 27610fd…:<檔>` 看了這 3 行：都是引用 `"unit_key": "Gossiping.M.1759730000.A.1B2"`（PTT post_id 範例）的敘述，不是密鑰；跟既有 5a4d91f、06f7081 那兩筆是同一種 generic-api-key 誤判 |
| 沒有放寬規則 | repo 沒有 `.gitleaks.toml`，PR 也沒新增；沒有動 CI workflow 或其他忽略清單；之後新增的真密鑰照樣會被抓到 |
| 說明清楚 | 檔頭的誤判說明補了「封存派工單引用的誤判內容」，符合驗收條件 2；回報 open_questions 逐筆列出 fingerprint、內容與理由（驗收條件 1） |
| 驗證 | worker 與 qa 都用 gitleaks 8.30.1（等於 CI 的 GITLEAKS_VERSION）跑出 0 筆；qa 另外換回 develop 的忽略清單做對照，得到 leaks found: 3，證明這 3 行剛好蓋掉那 3 筆。PR CI 的 Security 已 pass；Check、Integration Test 仍在跑，這個檔不影響它們 |

## 不擋合併的觀察

- 這已經是第 3 輪同一個字串 `unit_key: Gossiping.M…` 被抓：只要文件引用前一輪的誤判內容，就會產生新的 fingerprint。之後的文件、回報引用這個範例時，建議改寫成不像 `key: value` 的形式（例：只寫 post_id 值），或另開單評估加一條只比對這個值的 allowlist（這屬於改 gitleaks 規則，要另外 review）。本單照禁區的要求沒有這樣做，是對的。

問題數量：0
