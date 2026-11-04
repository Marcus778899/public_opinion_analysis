PASS d441efa

# 驗證 spec-release-order（docs）

## 範圍
- `git diff develop...HEAD --stat`：只有 `docs/development-spec.md`（4 行增、4 行減），與派工單「負責檔案」一致。
- diff 只動 4 處：第 111 行（第 2 章 semver／stage-3～6）、113 行（階段 6 以前的 tag 敘述）、366 行（階段 1 段落末句）、382 行（執行順序的延後合併敘述）。各階段範圍、驗收標準、進度表各列、執行順序表格均無變動（diff 中沒有表格列）。

## 驗收條件
1. 「執行順序」不再寫等階段 3、5 才合 main／補打 stage-3～8：第 382 行已改為「階段 1～6 以 v0.6.0 發版，之後每階段驗收後各發一版（見 D-003）」；第 111 行「stage-3～stage-6 照第 6 章原計畫補打」已改為由 v0.6.0 涵蓋、不補打。通過。
2. Stock 補標與階段 5 的 3 天驗收：順序表第「—」列與第 7 列原文未動；第 382 行補充「仍照排序之後再做」。通過。
3. `grep -n "stage-\|合進 .main\|合進.*main" docs/development-spec.md` 結果（111、113、366、382 行）逐條對照 D-003（階段 1～6 = v0.6.0、stage-3～6 不補打、之後每階段一版、Stock／3 天驗收之後再做）：一致。tag 實況 `git tag` = stage-1、stage-2，與「只打到 stage-2」一致。通過。

## 與 D-003 一致性
D-003 決定：v0.6.0 涵蓋階段 1～6、stage-3～6 不補打、之後每階段一版（階段 7 = v0.7.0）、Stock 重新標註與 3 天驗收照第 6 章之後再做。四處改動皆吻合。

## 檢查
`pre-commit run --files docs/development-spec.md`：trim trailing whitespace Passed、fix end of files Passed、ruff format Passed，其餘 Skipped（無對應檔）。
改動沒有新增或修改任何 markdown 連結；`git status --short` 乾淨。

## 備註（非 FAIL）
- 第 366 行位於第 6 章進度表下方（非表格內），屬「直接引用這段」的句子，改動範圍尚可接受；architect 若認為已觸及 D-004 凍結區，可由 manager 判斷。
- 第 554 行引用「見第 6 章執行順序」仍正確。
