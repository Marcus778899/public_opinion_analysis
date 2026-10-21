# 派工單 spec-release-order

- **類型**：docs
- **負責**：architect
- **目標**：開發規格第 6 章「執行順序」改成 develop 合進 main 不再等階段 3、5 驗收（D-003）
- **背景**：甲方 2026-10-20 修訂 D-003：階段 1～6 以 v0.6.0 發版，之後每階段一版；stage-3～6 tag 不補打。Stock 重新標註、階段 5 的 3 天驗收仍照原順序之後再做
- **設計依據**：`docs/decisions.md` D-003、D-004；`docs/development-spec.md` 第 6 章「執行順序」
- **相依**：無
- **負責檔案**：
  - `docs/development-spec.md`
- **禁區**：只改第 6 章「執行順序」中延後合併 main／打 stage tag 的敘述，以及其他直接引用這段的句子；不改各階段範圍、驗收標準與進度表（D-004 凍結）
- **驗收測試**：無
- **驗收條件**：
  - [ ] 「執行順序」不再寫等階段 3、5 通過才合進 main、補打 stage-3～8 tag；改為引用 D-003（每階段以 vX.Y.0 發版）；第 2 章約 111 行「stage-3～stage-6 照第 6 章原計畫補打」同步改成由 v0.6.0 涵蓋
  - [ ] Stock 重新標註、階段 5 的 3 天驗收的排序與說明保留
  - [ ] `grep -n "stage-3\|合進 .main" docs/development-spec.md` 剩下的結果都與 D-003 一致
- **驗證指令**：`grep -n "stage-\|main" docs/development-spec.md`
- **回報檔**：`reports/spec-release-order.json`

## 執行資訊（task.py 產生）

- Issue：#72
- 分支：`docs/spec-release-order`（從 develop 開出）
- 工作目錄：`.worktrees/spec-release-order`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
