APPROVE fc85d53

檢查項目：
- 變更檔：`.github/workflows/ci.yml`（負責檔案）、`tests/unit/acceptance/test_infra/test_compose_static.py`（驗收測試，qa 依派工單改寫）；沒有改到範圍外的檔案
- ci.yml 只改 Detect code changes 步驟的註解與 grep 規則：`^(docs/|\.agent/)|^[^/]+\.md$`，`docs/`、`.agent/`、根目錄 `*.md` 的略過行為不變；其他步驟、gitleaks、覆蓋率門檻沒動
- `grep -n "tasks/\|reports/" .github/workflows/ci.yml`：無結果
- 驗收測試要求 `docs/`、`.agent/`，並在移除 `.agent/` 前綴後檢查 `tasks/`、`reports/` 不出現（避免 `.agent/tasks/` 之類誤判），符合驗收條件；同檔其他測試沒變
- `uv run pytest tests/unit/acceptance/test_infra/test_compose_static.py -q`：33 passed
- PR CI：Check、Integration Test、Security 全 pass
- 沒有寫死設定值、沒有安全問題
