PASS eabd633

## 證據

- 變更：`git diff develop` 只動 `.gitleaksignore`，新增 2 行（d452b14 的 review.md:9、qa.md:17，generic-api-key）。
- 逐筆確認非真密鑰：`git show d452b14:tasks/backlog-cleanup-2026-10/gitleaks-v070-archive-ignore.{review,qa}.md | grep -n unit_key`，
  兩行都是中文敘述，引用 `"unit_key": "Gossiping.M.1759730000.A.1B2"`（PTT post_id 範例）；規則誤把 key 名稱 unit_key 當密鑰，無憑證字串。
- gitleaks 8.30.1（與 ci.yml GITLEAKS_VERSION 相同）：`gitleaks git --redact --no-banner .` 在分支上
  `225 commits scanned. no leaks found`，exit 0。
- PR #150 CI（run 39593362460）：Check pass、Security pass（25s）；Integration Test 當下仍 pending（與本單無關）。

## 備註（非 FAIL）

- fingerprint 綁 commit d452b14；PR 若 squash 改寫該 commit 不影響，因 d452b14 已在 develop；但若 develop 歷史被改寫則失效（worker 已在 open_questions 提出）。
- 我另試以空 ignore 檔 (`-i`) 想看原始 2 筆，gitleaks 仍讀 repo 根目錄 .gitleaksignore，故未能在本機重現原發現；以 CI 綠與內容檢查代之。
