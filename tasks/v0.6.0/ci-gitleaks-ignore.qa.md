PASS 0feb0d3

# 驗證 ci-gitleaks-ignore（chore，PR #77）

## 驗收條件
1. `.gitleaksignore` 新增 fingerprint 並在檔頭補說明：通過。`git diff develop...HEAD` 只動 `.gitleaksignore`（+2/-1）：新增
   `06f708152ca9324915476f75df04217a91feb4bd:docs/security/v0.6.0.md:generic-api-key:158`；檔頭 unit_key 那行補「（含資安報告引用的 PTT 文章 ID）」。
2. gitleaks 8.30.1 在分支 0 筆：通過（自己跑，版本與 ci.yml GITLEAKS_VERSION "8.30.1" 相同）。
   `gitleaks version` -> 8.30.1
   `gitleaks git --redact --no-banner .` -> `109 commits scanned. ... no leaks found`，exit=0

## 獨立確認
- 內容：`git show 06f7081:docs/security/v0.6.0.md | sed -n 158p` 是資安報告表格列，引用
  `"unit_key": "Gossiping.M.1759730000.A.1B2"`，PTT 文章 ID（與 5a4d91f 那筆同款），不是密鑰。
- 只多一筆：diff 只有一行 fingerprint 新增，其餘為註解；未改規則、未新增 `.gitleaks.toml`、workflow、其他忽略清單（非 `.gitleaksignore` 的 diff 為 0 行）。
- 工作樹乾淨（git status 無未提交變更）；無寫死設定值問題（僅忽略清單）。

## 限制
- 想在舊 ignore 下重現「修前有 1 筆」的對照，需 clone 到暫存目錄，被權限擋下，未做；修前狀態採派工單背景所述。修後 0 筆為實測。
