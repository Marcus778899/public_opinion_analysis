PASS dfee1ba

# init-exit-code 驗證（B，第二輪）

本單無程式改動，PR 只含鎖定的驗收測試（`git diff --stat develop...HEAD`：1 檔 342 行新增）。

## 實測
1. 在 `.worktrees/init-exit-code` 執行 `uv run pytest tests/unit/acceptance/init-exit-code -q`：`18 passed in 7.86s`。
2. `uv run ruff check .`：All checks passed；`ruff format --check .`：296 files already formatted。
3. `grep -rn "TODO(init-exit-code)" src tests tools`：無結果。
4. `docker compose -f infra/docker-compose.yaml --env-file .env --profile app ps -a`：radar_init `Exited (0)`；其他容器 uptime 19～20 小時，僅 kafka_3（8 分鐘）與 inference_shadow（137）異常，與回報「不能證明 Docker 整體重啟」的說法一致。
5. `infra/docker-compose.yaml` 的 init 服務（約第 143 行）為 `restart: "no"`，與回報排除項 (3) 一致。

## 回報檢查（reports/init-exit-code.json）
- 已改為「無法重現、原因未證實」，撤回「Docker 重啟造成」的推論，沒有再宣稱未證實的原因。
- 排除項：工具 main() 失敗路徑為 1（acceptance 18 個子行程測試涵蓋）、sh -c 串接的 alembic 失敗為 1、restart "no"、重跑 init 成功（Exited (0)）。有證據。
- 無法驗證項（UAT 當時 log 已不在）已明說；建議 F-3 標為「無法重現，暫不處理」並在再發生時保留 ps -a 與 init log。
- summary 已註明無程式改動；files_changed 維持 validate_report 要求。
- 依 manager 補充：不要求補單元測試、`tests/unit/tools` 為派工單筆誤，驗證以 acceptance 路徑為準。

## 限制
- 驗收條件「重跑 init 結束碼 0」：上一輪實跑成功回傳，本輪以目前 `Exited (0)` 與回報輸出為佐證，hook 不允許取 `$?`。
- 未對容器實際注入失敗，失敗路徑僅由子行程測試涵蓋。

## 問題
無。
