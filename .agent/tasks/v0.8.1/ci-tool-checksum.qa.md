PASS c61707f

# QA：ci-tool-checksum（PR #238）

## 1. 只改負責範圍
`git diff develop...HEAD`：只動 `.github/workflows/ci.yml`（+7/-1），且只在 Security job：新增 `GITLEAKS_SHA256`、`OSV_SCANNER_SHA256`，gitleaks 改成先下載成檔、`sha256sum -c -`、再解壓，osv-scanner 下載後加 `sha256sum -c -`。版本號、掃描設定、忽略清單、其他 job 皆未動。`gh pr view 238` 的檔案清單也只有該檔，head = c61707f。

## 2. checksum 獨立取自官方 checksums 檔
- https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_checksums.txt
  `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb  gitleaks_8.30.1_linux_x64.tar.gz`
- https://github.com/google/osv-scanner/releases/download/v2.6.0/osv-scanner_SHA256SUMS
  `ca69b3d3cd08f889a49dc0a383122f71cc528b83803671df5fd874d97485b108  osv-scanner_linux_amd64`
兩者與 ci.yml 寫死的值完全相同。

## 3. 本機實際下載並比對
```
gl.tgz: OK
osv: OK
```
## 4. 格式正確但值不符（64 個 a）
```
gl.tgz: FAILED
shasum: WARNING: 1 computed checksum did NOT match
exit=1
osv: FAILED
shasum: WARNING: 1 computed checksum did NOT match
exit=1
```
步驟在 GitHub Actions 的 bash（`-e`、pipefail）下，`sha256sum -c` 非 0 會使該步驟失敗；gitleaks 的 tar 與執行都在比對之後。

## 5. CI
`gh pr checks 238`（等全部跑完後）：
```
Check	pass	1m34s
Integration Test	pass	3m21s
Security	pass	31s
```
Security log 可見 `.../gitleaks.tar.gz: OK` 與 `.../osv-scanner: OK`，確認 CI 上比對真的有執行。

## 備註（不構成 FAIL）
- CI 上未實際推一次壞雜湊去看變紅，負向行為以本機 shasum 確認（sha256sum 語意相同）。
- 無寫死 port／網址／token 問題；URL 與版本已是既有寫法。
