APPROVE ccfff0e

# bert-derive-max-len code review 第 2 輪（PR #203）

上一輪 APPROVE @ 87e44d4（實作、驗收條件對照不變，本輪不重複）；本輪只看新 commit ccfff0e 與派工單「追加 2026-10-28」。

## 檢查範圍

| 項目 | 結果 |
|---|---|
| 87e44d4..ccfff0e 改動 | 只有 `tests/unit/ml/training/test_derive_model.py`（+44/-1），在負責檔案內；`src/`、驗收測試目錄、其他檔案未動 |
| 追加要求：同程序補測試、不改驗收測試與程式行為 | 符合：新增 4 個單元測試直接呼叫 `derive_model()`／`main()`，程式碼零變動 |
| 新測試是否真的測到行為 | `test_derive_card_without_max_len_raises`（第 35 行，card 無 `max_len` 拒絕）；`test_derive_copy_failure_cleans_staging_and_reraises`（第 60–62 行，複製失敗清掉暫存並往上丟，斷言目錄只剩來源）；`test_main_success_creates_target`、`test_main_rejected_exits_nonzero_with_one_line`（第 68–77 行，成功建立目標、拒絕時 `SystemExit` 訊息以 `error: ` 開頭）。皆有實質斷言，非只為執行行數 |
| 測試規範 | 不連網路、只用 `tmp_path`；命名 `test_<情境>_<預期>`；monkeypatch 自動還原 |

## 實跑（worktree）

- `uv run pytest -q tests/unit/acceptance/bert-derive-max-len tests/unit/ml/training/test_derive_model.py --cov=radar.ml.training.derive_model --cov-report=term-missing`：25 passed；`derive_model.py` 61 行漏 1 行，98%，只漏第 81 行（`if __name__ == "__main__": main()`）
- `uv run ruff check src tests`：All checks passed；`uv run ruff format --check src tests`：278 files already formatted

## 備註

- review 當下 PR 的 CI `Check`、`Integration Test` 尚未完成（Security 已過）；合併前以 CI 覆蓋率閘門結果為準。本機量得改到行 60/61 已覆蓋，應高於 80%。
