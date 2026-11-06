PASS f470481

## 範圍
review 退回後新 commit f470481（相對 a00da90 只改 infra/docker-compose.yaml：connect 補三個 CONNECT_{CONFIG,OFFSET,STATUS}_STORAGE_MIN_INSYNC_REPLICAS: '1'，註解改為 RF 與 min.isr）。前次 qa 其餘項目未變動；本次重跑全部。

## 實際執行（PYTHONPATH=worktree/src，確認 radar 從 .worktrees/connect-resilience/src 載入）
- 驗收測試 acceptance/connect-resilience + infra-secret-guard + init-exit-code：89 passed
- tests/unit 全部：1942 passed（-n 4）
- ruff check：All checks passed；ruff format --check：330 files already formatted
- grep TODO(connect-resilience) src tests：無結果
- 覆蓋率（cdc、common、tools 單元＋驗收）：connect.py 99%（缺 62）；watchdog.py 79%，缺的行為 main()/既有迴圈等原有程式（392-454 等），新增的 MissingWatch 邏輯有測試
- compose diff 確認三個 min.isr 均為 '1'，與 RF '2' 並列，符合驗收條件「RF=2、min.isr=1」與 review 要求
- 無寫死 port／URL／token；新設定已在 .env.example 選填註解
- CI（gh pr checks 296）：Check pass、Security pass、Integration Test 當時 pending（非本次判定依據）

## 未實機驗證（接受，已列入 stability-dev-verify）
compose healthcheck／init 實機流程、Connect 實際套用 min.isr（以 review 引用 KIP-605 原始碼為準）。
