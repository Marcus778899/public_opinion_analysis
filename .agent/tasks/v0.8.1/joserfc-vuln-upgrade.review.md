APPROVE f7b6011

# Review joserfc-vuln-upgrade（PR #275）

| 檢查項目 | 結果 |
|---|---|
| 改動範圍 | `gh pr diff 275` 只動 `uv.lock`（+3/-3），在派工單負責檔案內；沒動 pyproject.toml、osv-scanner 設定、忽略清單 |
| 驗收條件①版本 | joserfc 1.7.5 → 1.7.7，≥ 修正版 1.7.6（GHSA-9pg5-8c7x-5hfx）；只改 version、sdist、wheel 三行，來源仍是 pypi.org，hash 齊全 |
| 禁區：不升其他套件 | 其他套件與 authlib 未變；joserfc 的 dependencies 仍只有 cryptography，沒有帶進新相依 |
| 驗收條件②單元測試 | worker 與 qa 各自跑 `uv run pytest tests/unit -q`，1886 passed |
| 驗收條件③CI | `gh pr checks 275`：Check、Integration Test、Security 全 pass；qa 證據記錄 osv-scanner `No issues found` |
| 寫死設定、安全問題 | 只有 lock 檔，無 |

備註（不影響結論）：派工單與 PR 標題寫 1.7.6，實際解析到 1.7.7（`uv lock --upgrade-package` 取最新版）；條件寫「1.7.6 以上」，符合。
