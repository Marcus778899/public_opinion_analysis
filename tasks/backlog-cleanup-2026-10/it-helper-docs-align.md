# 派工單 it-helper-docs-align

- **類型**：test
- **負責**：backend
- **通道**：fast
- **目標**：收尾整合測試的 review 建議，並修掉 #126 剩下的 retention 偶發失敗
- **背景**：①it-helper-mv-filter（PR #141）review 的 3 條非阻擋建議：helper 加 NOTE 寫明依賴 `*_queue` 命名、Kafka 物件只用 CREATE／DROP；開發規格 7.26 實作補充 ④ 補 `is_current` 另查 Kafka 物件；`tests/integration/test_parallel_isolation.py` 的 `without_kafka` 斷言與新語意不一致（見 tasks/it-helper-mv-filter.review.md 或 reports/）。②#126：PR #138 修了 partition 數讀到舊值，2026-10-21 又出現 `retention.ms` 讀到舊值（issue #126 留言）。③integration-flaky-tests review 建議：`cdc/test_slot.py` 約第 58 行 `conn` 參數補型別標註
- **設計依據**：`docs/development-spec.md` 7.26；`reports/it-helper-mv-filter.review.md`；issue #126
- **相依**：無
- **負責檔案**：
  - `tests/helpers/clickhouse.py`
  - `tests/integration/test_parallel_isolation.py`
  - `tests/integration/common/test_topics_apply.py`
  - `tests/integration/cdc/test_slot.py`
  - `docs/development-spec.md`
- **禁區**：helper 只加註解，不改行為；不改 `src/`、`tools/`；不刪測試、不放寬斷言、不加固定 sleep 或 retry 掩蓋（要等就用條件式等待，同 PR #138 的 `wait_until`）；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] `test_parallel_isolation.py` 的 `without_kafka` 斷言改成符合新語意（只略過 Kafka engine 表與讀 `*_queue` 的 MV），並說明改法
  - [ ] `test_topics_apply` 的 retention 斷言等到新設定傳播後再判斷；回報寫根因
  - [ ] helper NOTE、開發規格 7.26 ④、`conn` 型別標註完成
  - [ ] 跑前 `docker compose ls` 確認沒有其他堆疊；`docker compose --env-file .env -f .worktrees/it-helper-docs-align/compose.yaml run --rm test` 全新堆疊連跑 2 次全過，做完 `down -v`
  - [ ] `make check` 通過；PR 的 CI 全綠
- **驗證指令**：`make check`；上面的 compose 指令
- **回報檔**：`reports/it-helper-docs-align.json`

## 執行資訊（task.py 產生）

- Issue：#147
- 分支：`test/it-helper-docs-align`（從 develop 開出）
- 工作目錄：`.worktrees/it-helper-docs-align`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
