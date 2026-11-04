APPROVE a1e7af9

## 檢查項目

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改了 `infra/docker-compose.yaml` 和 `docs/development-spec.md`；兩個測試檔都在本單的驗收測試範圍裡（`kafka-port-bind-local/` 是 qa 新寫的；`infra-secret-guard/test_compose_secret_guard.py` 依仲裁 TEST_WRONG 改寫，只改了參數化的期望值和測試名稱） |
| 禁區 | 沒有改到 `.env.example`、listener 設定、其他服務的 ports、`compose.yaml`、`compose.ci.yaml`、e2e compose |
| 驗收條件 1 | kafka_1～3 都改成 `127.0.0.1:<port>:<port>`；compose 裡每一個 ports 項目都帶 `127.0.0.1:`（grep 過全部 ports 段落） |
| 驗收條件 3 | 開發規格寫了 Kafka 只綁本機、用 `localhost:9092,9094,9096` 連、`KAFKA_EXTERNAL_HOST` 的意義，全文只寫在一處；7.20 步驟 6 改成「至少 1 則警示（文章或看板）」，看法保留了 |
| 驗收條件 4 | `uv run pytest tests/unit -q` 結果：1890 passed |
| 寫死設定、安全 | 沒有新加的設定值；這次改動是在縮小對外暴露面 |
| 測試是否測到驗收條件 | 有：測了 ports 的寫法、沒寫 IP 的項目、0.0.0.0、規格的文字、步驟 6 |

## 不擋合併的建議

- `docs/development-spec.md:949`：Kafka 綁本機的說明放在 7.20 步驟 3 的括號裡，同一句後面又寫了「本機執行 `KAFKA_BOOTSTRAP_SERVERS` 用 `localhost:9092,…`」，兩句意思重複，而且這個位置不好找。以後可以把綁本機的說明搬到 1.3 或基礎設施段落，步驟 3 只引用那一處。
- 驗收條件 2（`docker compose … config`）在 sandbox 裡沒有跑；靜態 grep 和驗收測試已經涵蓋同樣的事實。
