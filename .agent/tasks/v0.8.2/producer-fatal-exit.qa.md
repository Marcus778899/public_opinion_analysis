PASS c06e86b

驗證（worktree .worktrees/producer-fatal-exit，PYTHONPATH=<worktree>/src，radar 確認從 worktree 載入）

- `pytest tests/unit/acceptance/producer-fatal-exit tests/unit/common/kafka tests/unit/collector/test_scheduler.py tests/unit/api -q` -> 209 passed
- 全部單元測試（`pytest tests/unit`，含 acceptance）-> 1928 passed in 196.91s
- `ruff check .` -> All checks passed；`ruff format --check .` -> 329 files already formatted（.venv 無 mypy，未跑）
- 改到檔案覆蓋率：producer.py 100%；scheduler.py 79%、api/main.py 67%，未涵蓋行為既有的 lifespan／main 主迴圈，本單新增的 on_fatal、_logged、handle_producer_fatal、exit_for_restart 皆有覆蓋
- `grep TODO(producer-fatal-exit) src tests` -> 無結果

驗收條件對照
1. 三種入口（produce 例外、delivery callback、error_cb）丟 ProducerFatalError(Exception)，不繼承 KafkaException：程式碼與驗收測試確認
2. fatal 後 flush 立即丟、非 fatal 錯誤（DeliveryError、TimeoutError、BufferError 重試）行為不變：測試通過
3. scheduler 列表任務／due_posts／sync_boards／lock 經 _logged(on_fatal) 記 CRITICAL、shutdown、main 重新丟出；仲裁後 wired fixture 以 log._resolve 收集，測試通過；BatchConsumer 不 commit 並結束：驗收測試通過
4. API handler 回 503，BackgroundTask 先 log.close() 再 os._exit(70)：測試通過
5. 單元測試、lint 通過

備註（非 FAIL）：bot、watchdog 的 `except Exception` 不在本單負責範圍（禁區：不改其他服務入口）。
