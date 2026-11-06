APPROVE c61707f

# Code review：ci-tool-checksum（PR #238，對 develop）

| 檢查項 | 結果 |
|---|---|
| 負責檔案 | 只改 `.github/workflows/ci.yml`（+7/-1），且只在 Security job 的 env 與兩個下載步驟；其他 job、工具版本、gitleaks／osv-scanner 掃描設定與忽略清單都沒動 |
| checksum 來源 | 我自己重新抓官方 `gitleaks_8.30.1_checksums.txt`（linux_x64.tar.gz）與 `osv-scanner_SHA256SUMS`（linux_amd64），兩個值跟 ci.yml 寫死的完全一樣 |
| 失敗語意 | `echo "<hash>  <檔案>" \| sha256sum -c -`：管線的結束碼取最後一個指令（sha256sum），不需要 pipefail；預設 shell 是 `bash -e`，不符就讓該步驟失敗。gitleaks 改成先下載成檔、比對完才 `tar` 並執行；osv-scanner 比對完才 `chmod +x` 並執行。變數是空的話會變成「no properly formatted checksum lines」，同樣失敗（fail closed） |
| 寫死設定 | 只新增 checksum 常數，跟版本變數放在一起，註解寫了來源與升版時要一起更新；沒有 secret、port、網址的問題 |
| 驗收條件 | ① 比對過了才執行：成立 ② 官方來源與比對輸出：qa 證據 §2–§4，我也獨立確認了 ③ CI Security job 綠燈：`gh pr checks 238` 的 Security 是 pass |
| 測試 | 這張單沒有驗收測試目錄（chore）；負向行為只在本機用 shasum 驗過（qa 備註）。這點可以接受，不另外要求 |

問題：0
