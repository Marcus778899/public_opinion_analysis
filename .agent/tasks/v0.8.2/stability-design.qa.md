PASS 12ce241

## 範圍檢查
- git diff --name-only develop...HEAD：docs/development-spec.md、docs/domain/README.md、docs/domain/glossary.md、docs/realtime-sentiment-radar-design.md；皆在負責檔案內；非 docs 檔案：無（src、tests、infra、tools 皆未動）；worktree 無未提交變更。

## 檢查
- pre-commit run --all-files：trailing whitespace、end of files、check yaml、ruff、ruff format、bandit 全 Passed
- uv run pytest tests/unit -q -n auto：1890 passed in 51.85s

## 驗收條件
1. 每個問題（#281、#282、#289、#262、#268、小項）的修法、行為變更、錯誤處理：開發規格 7.30 A～F 皆有。通過
2. #282 操作步驟（備份、reassignment、驗證、回復）與 compose／建 topic 對應改法：7.30 B 步驟 0～7、回復、compose 三個 RF 與 min.isr、healthcheck、init 相依、topics.yaml 不管。通過
3. 每張實作單的驗收測試目錄與受影響既有驗收測試：派工順序表 9 張皆有；我抽查引用的既有測試檔與函式名（test_guard_init_depends_on_unchanged、test_connector_task_failed_exits_nonzero_and_logs_step_and_reason、WARNING_KEYWORD、import-model-hardening 的 test_cli_*、test_ci_integration_first_step_diffs_changed_files）皆存在。通過
4. 派工順序（task_id、負責、通道、平行、負責檔案、驗收測試目錄）與需調查、待決定、自行決定三表：皆有。通過

## 其他
- 無新增 TODO 標記、無寫死的設定值或密鑰；文件間（設計文件 4.2、4.4、6.4、8.2、10.3、domain）與 7.30 一致。
- 備註（非 FAIL）：文件為「規劃」目標行為，實作單合併前文件與程式暫不一致，已在 7.30 註明。
