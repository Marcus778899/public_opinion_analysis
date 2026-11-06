# 派工單 gitleaks-allowlist-boundary

- **類型**：chore
- **負責**：backend
- **目標**：gitleaks 的 revision 放行規則改成整段變數名比對，不再因為名稱裡含 sha／rev 子字串就放行（#171）
- **背景**：D-026 放行「變數名含 rev/revision/commit/sha，且值是 40 位小寫 hex」。現在的 regex 用子字串比對，所以 `SHARED_SECRET`、`PREVIOUS_API_KEY` 這類名稱的真密鑰也會被放行。來源 reports/gitleaks-revision-allowlist.qa.md、.review.md 的非阻擋觀察。
- **設計依據**：#171；D-026；`.gitleaks.toml`
- **相依**：無
- **負責檔案**：
  - `.gitleaks.toml`（只限 D-026 那條 revision allowlist）
  - `tests/unit/test_gitleaks_allowlist.py`（新檔：讀 `.gitleaks.toml` 的 regex，測放行與不放行的名稱）
- **禁區**：不改其他 allowlist、`.gitleaksignore`、CI；不擴大 D-026 的放行範圍
- **驗收測試**：無
- **驗收條件**：
  - [ ] repo 現有合法的 revision 變數（例 `*_REVISION`、`rev=`、`sha=`、`commit_sha`）照樣放行：本機跑 `gitleaks git --redact --no-banner .`（沒有安裝就用 `gitleaks dir`），結果跟改之前一樣沒有發現
  - [ ] `SHARED_SECRET`、`PREVIOUS_API_KEY`、`REVOKE_TOKEN` 這類名稱加上 40 位小寫 hex，不會被這條規則放行（有單元測試）
  - [ ] `make check` 通過；PR 的 CI Security job 是綠的
- **驗證指令**：`uv run pytest tests/unit/test_gitleaks_allowlist.py`；`make check`；附上 gitleaks 的執行輸出
- **回報檔**：`reports/gitleaks-allowlist-boundary.json`

## 執行資訊（task.py 產生）

- Issue：#240
- 分支：`chore/gitleaks-allowlist-boundary`（從 develop 開出）
- 工作目錄：`.worktrees/gitleaks-allowlist-boundary`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

### reports/gitleaks-allowlist-boundary.review.md

REQUEST_CHANGES 5d93505

# Review gitleaks-allowlist-boundary（PR #241）

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 變更檔是否只在負責檔案內 | 是：只有 `.gitleaks.toml`（只動 D-026 那條的 description 與 regex）、`tests/unit/test_gitleaks_allowlist.py` |
| 禁區（其他 allowlist、`.gitleaksignore`、CI） | 沒動 |
| 收緊子字串比對（`SHARED_SECRET`、`PREVIOUS_API_KEY`、`REVOKE_TOKEN`、`SECRETSHA`） | 已收緊，有單元測試 |
| 現有合法 revision 變數（`MACBERT_REV`、`CKIP_PR_COMMIT`、`GOOGLE_TOKENIZER_REV`） | 新舊 regex 都放行；PR CI 的 Check、Integration Test、Security 三個都 pass |
| 值的條件（40 位小寫 hex、前後邊界） | 沒改 |
| **新放行的字串是不是舊放行字串的子集（不擴大範圍）** | **不是，見下面** |

我用 Python 拿新舊 regex 比對同一組字串（`h` = 40 位小寫 hex）：

| 字串 | 舊 | 新 |
|---|---|---|
| `"revision": "h"` | 不放行 | 放行 |
| `"api_key_sha": "h"` | 不放行 | 放行 |
| `'secret_token_rev' = 'h'` | 不放行 | 放行 |
| `rev"=h` | 不放行 | 放行 |
| `MACBERT_REV = "h"`、`x.sha=h`、`token-rev: h` | 放行 | 放行 |

原因：新 regex 在關鍵字和 `[:=]` 中間多了 `["']?`。舊 regex 在關鍵字後面只接受 `[a-zA-Z0-9_]*`，名稱後面緊接著引號（JSON／dict key、帶引號的 YAML key）一律不放行。這次新增了一類以前會被擋下的字串，是擴大放行範圍，違反派工單禁區「不擴大 D-026 的放行範圍」。回報的 open_questions 也沒有提到這點，qa 證據檔同樣沒有抓到。repo 現有的 revision 變數都不需要這個引號分支（上表三個名稱都不帶引號）。

## 要改的地方

1. `.gitleaks.toml:16` — regex 裡的 `["']?` 讓「名稱後面緊接引號」這類字串變成新放行（例 `"api_key_sha": "<hex40>"`），擴大了 D-026 的範圍 — 拿掉 `["']?`，改成 `(?i:(?:^|[^a-z0-9])(?:rev|revision|commit|sha))\s*[:=]+…`（後半段不變）；這樣新規則放行的字串一定是舊規則放行字串的子集。如果真的需要放行帶引號的 key，那是新的放行範圍，要回報 manager，不能在這張單裡自己加。
2. `tests/unit/test_gitleaks_allowlist.py:31` — `'"revision": "{HEX40}"'` 斷言放行，等於把這次擴大的範圍寫成預期行為 — 從 allowed 清單移除，改放進不放行清單（或另寫一個測試，斷言帶引號的名稱不放行）；建議再加一個測試，對一組樣本字串斷言「新 regex 有匹配 ⇒ 舊 regex（寫在測試裡當常數）也有匹配」，把不擴大範圍固定下來。

## 不阻擋的觀察

- 單元測試用的是 Python `re`，gitleaks 用的是 Go RE2。這個 regex 用到的語法（`(?i:…)`、否定字元類別、`\s`）兩邊行為一樣，而且 CI Security job 是 pass，所以可以接受。
- 本機沒有跑 gitleaks（sandbox 裡沒有安裝），驗收條件 1 靠的是 CI Security job 的綠燈。改完之後一樣要看 CI Security 有沒有 pass。
- 名稱以 sha／rev 結尾的密鑰（例 `SECRET_SHA=<hex40>`）還是會放行。舊規則本來就放行這種寫法，這也在 D-026 的文字範圍內，所以不算擴大。
