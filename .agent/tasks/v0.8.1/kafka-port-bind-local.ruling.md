TEST_WRONG 6d00d5c

驗收測試 lock 檢查：跟 lock（commit 32ef833）時一樣，沒被改過

| 測試 | 契約條文 | 判定與理由 |
|---|---|---|
| `tests/unit/acceptance/infra-secret-guard/test_compose_secret_guard.py::test_guard_kafka_ports_unchanged` | D-039（kafka_1～3 改綁 127.0.0.1）；派工單驗收條件 1（ports 都是 `127.0.0.1:<port>:<port>`） | 錯。測試鎖定舊值 `"9092:9092"`、`"9094:9094"`、`"9096:9096"`，與 D-039 直接矛盾，任何符合本單的實作都會讓它失敗。應改為：參數化的期望值改成 `"127.0.0.1:9092:9092"`、`"127.0.0.1:9094:9094"`、`"127.0.0.1:9096:9096"`（寫法同同檔 `test_guard_api_depends_only_on_init_and_port_unchanged` 的 `127.0.0.1:8000:8000`），測試名稱可維持或改為 `test_guard_kafka_ports_bound_local`。 |

範圍提醒：此測試檔不在本單「驗收測試」（`tests/unit/acceptance/kafka-port-bind-local/`）範圍內，manager 需先把 `tests/unit/acceptance/infra-secret-guard/test_compose_secret_guard.py` 追加進本單範圍，由 qa 依上述改寫後重新 lock。

契約問題：設計／派工單未列出「受影響的既有驗收測試」，漏了這個舊單測試；非決策分級四類，不需 D-編號。
