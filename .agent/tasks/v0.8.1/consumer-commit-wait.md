# 派工單 consumer-commit-wait

- **類型**：fix
- **負責**：backend
- **目標**：`BatchConsumer._commit()` 重試等待改成分段 sleep，消除與 signal handler 互等的死結可能（#146）
- **背景**：見 #146（現象、影響、改法、驗收都寫在 issue 內，照 issue 的改法做）
- **設計依據**：#146；`docs/development-spec.md` 2.2「commit 失敗」列（行為不變，不需改文件）
- **相依**：無
- **負責檔案**：
  - `src/radar/common/kafka/consumer.py`
  - `tests/unit/common/kafka/`
  - `tests/unit/acceptance/consumer-commit-wait/`
- **禁區**：不改 commit 重試次數與退避策略；不改其他 consumer
- **驗收測試**：
  - `tests/unit/acceptance/consumer-commit-wait/`
- **驗收條件**：
  - [ ] 單元測試：等待中途 stop，最晚一段 sleep（≤ 0.5 秒，用注入的 fake sleep／clock 不真的等）內結束、`commits == 0`、不拋出、consumer 已 close
  - [ ] `grep -n "_stop.wait" src/radar` 沒有結果
  - [ ] 驗收測試、`make check` 通過；`grep -rn "TODO(consumer-commit-wait)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/consumer-commit-wait tests/unit/common`；`make check`
- **回報檔**：`reports/consumer-commit-wait.json`

## 執行資訊（task.py 產生）

- Issue：#208
- 分支：`fix/consumer-commit-wait`（從 develop 開出）
- 工作目錄：`.worktrees/consumer-commit-wait`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
