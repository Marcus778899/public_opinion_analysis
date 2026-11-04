APPROVE 70e6f5c

# Review PR #185（deps-authlib-upgrade）

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改 `uv.lock`（+3／-3），在派工單負責檔案內；`pyproject.toml` 未改 |
| 驗收：authlib ≥ 1.9.1 | 1.8.0 → 1.9.1；sdist／wheel URL 與 sha256 同步更新 |
| 驗收：其他套件無不必要變動 | diff 只有 authlib 區塊；相依 cryptography、joserfc 未變；沒有新增套件 |
| 驗收：osv-scanner 無 authlib 漏洞 | 本機無工具（回報已說明），依派工單以 CI 為準：Security pass |
| 驗收：make check | worker 與 qa 皆 1348 passed；CI Check pass、Integration Test pass（含 avro／schema registry） |
| 禁區 | 未改程式碼、未升其他套件 |
| 寫死設定、bug、安全 | 無程式變動；lock 來源為 pypi 官方 registry，hash 齊全 |
| 測試 | 驗收測試：無（chore）；以既有單元／整合測試與 CI 為準 |

問題數量：0
