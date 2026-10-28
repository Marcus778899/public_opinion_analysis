# 派工單 bert-evaluate-report-fix

- **類型**：fix
- **負責**：backend
- **目標**：`evaluate` 產生的 `evaluation.md` 修掉寫死的標題與 0 篇列，並多記「載入模型後 RSS」，讓甲方重跑時能分開看模型載入與推論的記憶體
- **背景**：甲方 2026-10-28 對 4 個 BERT 模型跑 evaluate，報告分數節標題都是「## Baseline」，「LLM 標註者 vs 人工」全是 0 篇的列（且每個看板都被標「樣本少」）。原因與做法已由 architect 定案（#193），見設計依據
- **設計依據**：`docs/development-spec.md` 7.27「評估結果與進 shadow 的調整」的「修正單」表 `bert-evaluate-report-fix` 列（負責檔案與驗收條件以該列為準）
- **相依**：無
- **負責檔案**：
  - `src/radar/ml/training/evaluate.py`
  - `tests/unit/ml/training/test_evaluate.py`
- **禁區**：`measure_runtime` 簽名不變；`RuntimeStats` 只能新增有預設值的欄位；不改分數計算；不改驗收測試
- **驗收測試**：
  - `tests/unit/acceptance/bert-evaluate-report-fix/`
- **驗收條件**：
  - [ ] 分數節標題改為「## 模型分數」
  - [ ] 某標註者與人工重疊 0 篇時不列 0 篇的列，改一行說明「`<labeler>` 在人工測試集沒有 `<label_version>` 的標註」；有篇數的照舊
  - [ ] CPU 節多一列「載入模型後 RSS」（`main()` 在 `load_classifier` 後讀 `_peak_rss_mb()`）
  - [ ] 驗收測試、`uv run pytest tests/unit/ml/training/test_evaluate.py`、`make check` 通過；`grep -rn "TODO(bert-evaluate-report-fix)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/bert-evaluate-report-fix tests/unit/ml/training/test_evaluate.py`；`make check`
- **回報檔**：`reports/bert-evaluate-report-fix.json`

## 執行資訊（task.py 產生）

- Issue：#194
- 分支：`fix/bert-evaluate-report-fix`（從 develop 開出）
- 工作目錄：`.worktrees/bert-evaluate-report-fix`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
