APPROVE 0feb0d3

# Review PR #77（ci-gitleaks-ignore）

| 檢查項目 | 結果 |
|---|---|
| 改到的檔案 | 只有 `.gitleaksignore`（+2/-1），與派工單的負責檔案一致；沒有動 workflow、`.semgrepignore`，也沒有新增 `.gitleaks.toml` |
| 新增的 fingerprint 範圍 | `06f708152ca9324915476f75df04217a91feb4bd:docs/security/v0.6.0.md:generic-api-key:158`，鎖定 commit、檔案、規則、行號四項，只忽略那一筆發現，規則本身沒有放寬 |
| 誤判理由 | 實際看過 `git show 06f7081:docs/security/v0.6.0.md` 第 158 行：是資安報告表格裡引用的 `"unit_key": "Gossiping.M.1759730000.A.1B2"`，屬於 PTT 文章 ID（`post_id` 格式），不是密鑰；和既有的 5a4d91f 那筆是同一種誤判 |
| 檔頭說明 | unit_key 那行補上「（含資安報告引用的 PTT 文章 ID）」，符合驗收條件 1 |
| 驗收條件 2（掃描 0 筆） | qa 用 gitleaks 8.30.1（與 ci.yml 的 GITLEAKS_VERSION 相同）在 0feb0d3 實測 `no leaks found`，exit 0；worker 回報的結果也一樣 |
| 寫死的設定值、安全問題 | 無；這次只改忽略清單 |

## 限制

- review 環境的 PATH 上沒有 gitleaks，我沒有自己重跑掃描，驗收條件 2 以 qa 證據為準
