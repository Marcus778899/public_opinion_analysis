PASS a213c09

## 驗收條件對照

- 標題改「## 模型分數」：diff 確認 `render_markdown` 已改；驗收測試與新增單元測試通過
- 0 篇標註者：整體列與看板列都以 `a.n > 0` 過濾，0 篇者改輸出「`<labeler>` 在人工測試集沒有 `<label_version>` 的標註。」；`main()` 傳入 `card.label_version`；有篇數者照舊（既有測試仍過）
- 載入模型後 RSS：`main()` 在 `load_classifier` 後讀 `_peak_rss_mb()`，以 `dataclasses.replace` 寫入 `RuntimeStats.load_rss_mb`（有預設值 None）；CPU 節多一列，None 時不輸出；`measure_runtime` 簽名未動；分數計算未動
- `grep -rn "TODO(bert-evaluate-report-fix)" src tests`：無結果
- 禁區：驗收測試目錄無改動（僅 test commit 新增）

## 實際執行

`uv run pytest tests/unit/acceptance/bert-evaluate-report-fix tests/unit/ml/training/test_evaluate.py`
→ 30 passed in 0.34s

`uv run ruff check .` → All checks passed；`ruff format --check .` → 289 files already formatted

`uv run pytest tests/unit -q -n 4` → 1368 passed

`pre-commit run --all-files`（make check 的前半）→ 全部 Passed（trailing whitespace、end of files、yaml、ruff、ruff format、bandit）

## 備註（非 FAIL）

- `load_rss_mb` 取自 `ru_maxrss`（歷史峰值），載入後與推論前之間只有讀測試集，可視為載入後 RSS，與派工單指定做法一致
- `render_markdown` 的 `label_version` 預設空字串，未傳時說明會出現空的反引號；唯一呼叫端 `main()` 有傳，不影響
