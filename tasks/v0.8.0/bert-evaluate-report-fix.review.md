APPROVE a213c09

## 檢查範圍

PR #195（`fix/bert-evaluate-report-fix`，2 個 commit：68ddf0b test、a213c09 fix），對照派工單 `tasks/bert-evaluate-report-fix.md`、開發規格 7.27「修正單」`bert-evaluate-report-fix` 列。

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改 `src/radar/ml/training/evaluate.py`、`tests/unit/ml/training/test_evaluate.py`；驗收測試目錄只有 qa 的 `test(bert-evaluate-report-fix)` commit 動過 |
| 標題「## 模型分數」 | 符合 |
| 0 篇標註者 | 整體列與看板列都以 `a.n > 0` 過濾；0 篇者輸出「`<labeler>` 在人工測試集沒有 `<label_version>` 的標註。」；`main()` 傳 `card.label_version`；有篇數者照舊 |
| 載入模型後 RSS | `main()` 在 `load_classifier` 後立即讀 `_peak_rss_mb()`，以 `dataclasses.replace` 填入；CPU 節在峰值列前多一列，`None` 時不輸出 |
| 禁區 | `measure_runtime` 簽名未動；`RuntimeStats.load_rss_mb` 有預設值 `None`；分數計算未動；`render_markdown` 新增的 `label_version` 是 keyword-only 且有預設值，既有呼叫端不受影響 |
| 寫死設定 / 安全 | 無；只影響本機產生的 markdown |
| 測試是否測到驗收條件 | 驗收測試經 `main()` 端對端驗證三項條件（含載入 RSS 是在 `load_classifier` 之後的第一次讀值）；單元測試涵蓋有／無 `load_rss_mb` 與 0 篇說明 |
| CI | Check、Security 通過；Integration Test 在 review 時仍 pending（本 PR 不碰整合測試相關程式） |

## 非阻擋備註

- 所有標註者都是 0 篇時，「LLM 標註者 vs 人工」表只剩表頭、下方接說明行；不在驗收條件內，可讀性可接受
- `label_version` 預設空字串，未傳時說明會出現空反引號；唯一呼叫端 `main()` 有傳（qa 已記）
