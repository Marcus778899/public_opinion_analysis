APPROVE 7206572

# Review gitleaks-revision-allowlist（PR #170）

對照：派工單 `tasks/gitleaks-revision-allowlist.md`、D-026、D-018、調查報告 `reports/bert-shadow-inference.gitleaks.md`「修法選項」A、worker 回報、qa 證據（第二輪 PASS 7206572）。

## 檢查項目

| 項目 | 結果 |
|---|---|
| 改動範圍 | 只動 `.gitleaks.toml`（+6 行）；未碰 CI workflow、`.gitleaksignore`、gitleaks 版本，符合禁區 |
| D-018 保留 | `useDefault = true`、`^tasks/` 路徑排除原樣保留；沒有關閉或改寫任何規則 |
| 只限 generic-api-key | `targetRules = ["generic-api-key"]`，`regexTarget = "match"`：只比對該規則的 match 字串，其他規則（github-pat 等專用前綴）不受影響 |
| 值的範圍 | 剛好 40 位小寫 hex：引號包住，或無引號時後接非英數字元／行尾；RE2 無 lookahead，這個寫法正確。大小寫不分只套在名稱 `(?i:...)` |
| 名稱條件 | 名稱含 rev／revision／commit／sha（子字串），與 D-026 文字「變數名含」及甲方核可的選項 A 一致 |
| 寫死設定、密鑰引用 | 無；回報與 PR 說明沒有原文引用疑似密鑰 |
| CI | `gh pr checks 170`：Check、Integration Test、Security 全 pass |

## 我自己跑的驗證（gitleaks 8.30.1，`$TMPDIR/gitleaks/gitleaks`）

- worktree（HEAD 7206572）`gitleaks git --redact --no-banner .` -> `no leaks found`
- `$TMPDIR/rv170` 暫時 repo，隨機值，PR 設定 vs 只用預設規則：

| 情境 | 預設 | PR 設定 |
|---|---|---|
| GOOGLE_TOKENIZER_REV + 40 小寫 hex（雙引號） | 抓 | 放行（目標） |
| tokenizer_revision + 40 小寫 hex（YAML 單引號） | 抓 | 放行（目標） |
| TOKENIZER_REV + 48 hex | 抓 | 抓 |
| TOKENIZER_REV + 40 大寫 hex | 抓 | 抓 |
| TOKENIZER_REV + 40 hex 後接英文字 | 抓 | 抓 |
| API_KEY + 40 hex | 抓 | 抓 |
| 同一行先有 rev 變數、後有 api_key + 40 hex | 抓 | 抓 |
| SHARED_SECRET + 40 小寫 hex | 抓 | **放行** |
| PREVIOUS_API_KEY + 40 小寫 hex | 抓 | **放行** |

## 非阻擋（不影響本次結論）

名稱比對是子字串、無詞段邊界，`shared`（含 sha）、`previous`／`preview`（含 rev）這類名稱的真密鑰配 40 位小寫 hex 會被放過（qa 已記一項）。這落在 D-026 的文字「變數名含」與選項 A 已列、甲方已接受的剩餘風險「名稱同時含 token／key 與 rev／sha」之內，所以不判偏離決策。值得注意的是 `SHARED_SECRET`、`PREVIOUS_*`（金鑰輪替）是常見命名，舊式 40 hex token 也存在；若之後要收緊，可把名稱改成以 rev／revision／commit／sha 為詞段（前接 `_`、`.`、`-` 或開頭，後接 `_`、數字或名稱結尾），並保留 camelCase 寫法。收緊只會讓放行變少，屬於可逆細節，可開 issue 不必再問甲方。
