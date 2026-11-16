TEST_WRONG 3733ad2

驗收測試 lock 檢查：跟 lock（commit b8018db）時一樣，沒被改過。

| 測試 | 契約條文 | 判定與理由 |
|---|---|---|
| `tests/unit/acceptance/bbs-retest-tool/test_bbs_retest_acceptance.py::test_web_score_counts_boos_against_pushes_and_thirty_is_accepted` | `docs/development-spec.md` 7.31 G-2 檢查列：「網頁版各抓 1 次，推 − 噓 ≥ 30 … 任一不過就拒絕（exit 3），不寫 ledger」 | 測試錯。測試意圖（40−11=29 拒絕、40−10=30 通過）符合契約，但它傳 `tmp_path / "a"`、`tmp_path / "b"` 給 `_run`，`_run` 呼叫 `_write_p0(tmp_path)`，`_write_p0` 第 297 行 `first.mkdir(exist_ok=True)` 沒有 `parents=True`，父目錄 `a`、`b` 不存在，在進入工具前就 `FileNotFoundError`。與實作無關 |

## 測試應該怎麼改

- `tests/unit/acceptance/bbs-retest-tool/test_bbs_retest_acceptance.py` 第 297 行 `_write_p0` 的 `first.mkdir(exist_ok=True)` 改成 `first.mkdir(parents=True, exist_ok=True)`；其他不動，改完重新 lock

## 驗證

- 在 worktree 原樣執行：`uv run pytest tests/unit/acceptance/bbs-retest-tool/test_bbs_retest_acceptance.py::test_web_score_counts_boos_against_pushes_and_thirty_is_accepted -q` → `FileNotFoundError: .../test_web_score_counts_boos_aga0/a/first`，1 failed
- 把測試檔複製成暫存檔、只做上述一行替換後跑整個檔：`93 passed in 43.37s`（暫存檔已刪，worktree `git status` 乾淨）

## qa 項目

- 這次仲裁由 worker disputes 觸發，沒有 qa FAIL 證據檔要判

## 契約問題

- 無
