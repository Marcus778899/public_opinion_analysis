PASS 158b463

# certifi-security-bump 驗證證據

## 1. uv.lock diff 只有 certifi
`git diff develop...HEAD --stat`：`uv.lock | 6 +++---`（1 檔，3 增 3 刪）。
完整 diff 只動 `[[package]] certifi` 區塊的 version、sdist（url/hash/size/upload-time）、wheel（url/hash/size/upload-time）；
未動其他套件、pyproject.toml、src、tests、CI。`git status` 乾淨。

## 2. 版本 >= 2026.10.19
`uv.lock`：`name = "certifi"` / `version = "2026.10.19"`（舊 2026.7.22），滿足修 PYSEC-2026-4320 的下限。

## 3. make check（我自己執行）
exit=0；pre-commit 各項（trailing whitespace、end of files、check yaml、ruff、ruff format、bandit）Passed；
`uv run pytest tests/unit` -> `1066 passed in 3.23s`。

## 4. PR #103 CI（`gh pr checks 103 --watch`，等到全部結束，exit 0）
- Check: pass 45s
- Integration Test: pass 1m57s
- Security（osv-scanner）: pass 27s

## 邊界／其他
- 無寫死設定值（本單只動 lock）。
- 本機未跑 osv-scanner，Security 結論以 CI 為準（已綠）。
