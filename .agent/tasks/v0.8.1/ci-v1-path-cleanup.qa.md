PASS fc85d53
- 測試改寫：要求 docs/、.agent/，且移除 .agent/ 後不含 tasks/、reports/；同檔其他測試未動（diff 僅此段）
- ci.yml：grep -n "tasks/\|reports/" 無結果（exit 1）；僅改 Detect code changes 的註解與 regex
- uv run ruff check . -> All checks passed!
- uv run pytest tests/unit -q -> 1885 passed；test_infra 39 passed
- 規則抽測：docs/a.md、.agent/x、README.md 略過；tasks/a.md、reports/b、src/x.py、sub/README.md 判為 code；混合變更判為 code
- gh pr checks 279：Check、Integration Test、Security 全 pass
