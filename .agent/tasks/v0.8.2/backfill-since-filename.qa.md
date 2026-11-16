PASS 5df217b

## 驗證（commit 5df217b，worktree .worktrees/backfill-since-filename）

- `PYTHONPATH=$(pwd)/src make check`：`1981 passed in 93.14s`；`ruff check` All checks passed、`ruff format --check` 334 files already formatted
- `grep -rn "TODO(backfill-since-filename)" src tests`：無結果
- 整合測試 `docker compose ... run --rm test pytest tests/integration/acceptance/backfill-since-filename tests/integration/acceptance/crawl-backfill-depth tests/integration/collector -q -p no:xdist`：`33 passed in 4.37s`；已 `down -v`

## 驗收條件對照
- since = 最大檔名時間 - 10 分鐘（真 PG）：acceptance test_since_is_max_filename_epoch_minus_ten_minutes、整合 test_latest_post_since_uses_filename_epoch_not_created_at，通過
- created_at 2099 不影響：test_since_ignores_created_at_in_2099 通過
- 刪除文計入、無文章為 null、未來檔名以現在計並記 WARNING：對應 acceptance 測試皆通過（另有數值比較非文字比較、跨看板隔離）
- make check、整合測試通過：見上

## 檢查
- 程式（scheduler.py）使用 Core select、`to_timestamp(max(split_part(...)::bigint))`，與 7.30 E 行為一致；查詢逾時照拋（7.28 A 不變）；無寫死 port／網址／token
- 備註（非 FAIL）：worker 未跑 `ae ci coverage-gate`；新分支均有單元與整合測試涵蓋
- 備註：post_id 第三段非數字時 cast 失敗，會走 except 回 null 並記 WARNING（只讀第一頁，不停計時器）；post_id 由 parser 依 PTT 檔名產生，實務上為 epoch
