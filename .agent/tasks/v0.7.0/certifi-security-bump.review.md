APPROVE 158b463

# certifi-security-bump review（PR #103）

| 檢查項目 | 結果 | 依據 |
|---|---|---|
| 變更範圍只在負責檔案 | 通過 | `gh pr view 103 --json files`：只有 `uv.lock`（+3/-3），單一 commit `chore(certifi-security-bump): ...` |
| diff 只有 certifi | 通過 | 只改 `[[package]] certifi` 的 version、sdist、wheel；其他套件、`pyproject.toml`、`src/`、`tests/`、CI 都沒動 |
| 版本符合派工單 | 通過 | 2026.7.22 → 2026.10.19（派工單要求 ≥ 2026.10.19） |
| 來源 | 通過 | `source = registry https://pypi.org/simple`，url 在 `files.pythonhosted.org`，跟原本一樣 |
| hash／size 與 PyPI 一致 | 通過 | 對照 `https://pypi.org/pypi/certifi/2026.10.19/json`：wheel sha256 `42d35340…670e1b`、136464 bytes；sdist sha256 `035c1e85…a1ae`、137598 bytes；upload-time 也一致 |
| 新增相依（決策分級②） | 不適用 | 只升既有的間接相依，沒有新套件 |
| 文件同步 | 不需要 | `docs/`、`pyproject.toml`、README 都沒寫 certifi 版本；行為、資料流、API 都沒變 |
| 寫死設定、安全問題 | 無 | lockfile 版本更新，修 PYSEC-2026-4320 |
| 驗證 | 通過 | worker 與 qa 都跑過 `make check`（1066 passed）；PR CI 的 Check、Integration Test、Security（osv-scanner）都是 SUCCESS，worker open_questions 裡的 osv-scanner 疑問已由 CI 解決 |
