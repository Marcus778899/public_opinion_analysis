APPROVE f470481

## 檢查範圍

- 上一輪 REQUEST_CHANGES a00da90 之後的新 commit f470481（`git diff a00da90 f470481`），對照上一輪要修改的第 1 條、派工單驗收條件「三個內部 topic RF=2、min.isr=1」、開發規格 7.30 B、qa 結果 `.agent/reports/connect-resilience.qa.md`（PASS f470481）、worker 回報 `.agent/reports/connect-resilience.json`
- 上一輪其他項目已判定符合（見上一輪結果），這次只改 `infra/docker-compose.yaml`，其他檔案沒有變動

## 結果

| 項目 | 結果 |
|---|---|
| 上一輪第 1 條：補回 `CONNECT_{CONFIG,OFFSET,STATUS}_STORAGE_MIN_INSYNC_REPLICAS: '1'` | 已補，放在三個 `*_REPLICATION_FACTOR: '2'` 之後，`infra/docker-compose.yaml:353-355` |
| 註解同時說明 RF 與 min.isr | 已改（`:349`） |
| 負責檔案 | 只改 `infra/docker-compose.yaml` 的 `connect`，在負責範圍內 |
| 寫死設定 | 沒有新增 port、URL、secret |
| 回報 | open_questions 已改成「由原始碼確認會套用（KIP-605）」，不再列已知限制 |
| 驗收測試 | 沒被改；qa 重跑 89 passed，涵蓋 `test_internal_topic_min_insync_replicas_is_1_when_set` |
| CI（`gh pr checks 296`） | Check、Integration Test、Security 都 pass |

## 不算問題的備註

- compose healthcheck、init 流程、Connect 實際套用 min.isr 沒實機跑過，由 `stability-dev-verify` 演練（同上一輪）
