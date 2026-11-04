# 派工單 bert-shadow-gate-ruling

- **類型**：docs
- **負責**：architect
- **目標**：依 ckip fp32 重跑 evaluate 的結果，判定是否通過 7.27 順序 3 的進 shadow 門檻，並把「每批 < 30 s」是指 p50 還是最大值寫清楚，決定下一步走順序 6（啟動 shadow）或 4（截到 256）
- **背景**：甲方 2026-10-28 在 #195、#197 合併後重跑 `evaluate --model models/bert-ckip-202610280849`（主目錄 `models/bert-ckip-202610280849/evaluation.md`，直接讀）：macro-F1 0.612（與上次相同）；每篇 p50 258 ms、p95 305 ms；每批 p50 25.818 s、最大 30.456 s；載入模型後 RSS 689 MB、峰值 932 MB。F1 與 RSS 明確通過；耗時 p50 過、最大超過 30 s 0.456 s。7.27「自行決定」與順序表只寫「每批 < 30 s」，沒說用哪個統計量
- **設計依據**：`docs/development-spec.md` 7.27「自行決定」的「進 shadow 的門檻」列、「評估結果與進 shadow 的調整」（順序表、30 s 不放寬的理由）
- **相依**：無
- **負責檔案**：
  - `docs/development-spec.md`（7.27）
- **禁區**：不改程式；不推翻已定案決策
- **驗收測試**：無
- **驗收條件**：
  - [ ] 明確寫出門檻用的統計量與理由，並把這次結果填入順序表與結論，寫明下一步（順序 6 或 4）
  - [ ] 若走順序 6，列出啟動 shadow 時要觀察的項目（容器峰值記憶體、是否 OOM、補資料期間每批耗時）與甲方要做的步驟
- **驗證指令**：`pre-commit run --files docs/development-spec.md`
- **回報檔**：`reports/bert-shadow-gate-ruling.json`

## 執行資訊（task.py 產生）

- Issue：#199
- 分支：`docs/bert-shadow-gate-ruling`（從 develop 開出）
- 工作目錄：`.worktrees/bert-shadow-gate-ruling`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
