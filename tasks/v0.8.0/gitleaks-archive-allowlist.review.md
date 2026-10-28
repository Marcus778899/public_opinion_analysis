APPROVE 629b2ef

# Review PR #153 gitleaks-archive-allowlist（D-018）

## 檢查項目

| 項目 | 結果 |
|---|---|
| 變更檔案只限負責檔案 | 只有 `.gitleaks.toml`（新增）、`.gitleaksignore`；沒動 CI workflow、gitleaks 版本、`scripts/`、`.claude/`、`contracts/` |
| 排除範圍只限 `tasks/` | `[[allowlists]] paths = ['''^tasks/''']`，有 `^` 錨定；qa 反向測試確認 `docs/tasks/`、`nottasks/`、`src/` 仍會被抓，只有開頭為 `tasks/` 的路徑被略過。沒有 `regexes`、`stopwords`、`commits` 等其他放寬條件 |
| 預設規則完整保留 | `[extend] useDefault = true`，檔內沒有任何 `[[rules]]`，也沒有 `disabledRules`；qa 以三種預設規則（aws-access-token、generic-api-key、github-pat）在 `tasks/` 以外都抓得到佐證 |
| 設定會被 CI 載入 | CI 以 `gitleaks git … .` 掃 repo 根目錄，gitleaks 會自動讀 source 根目錄的 `.gitleaks.toml`；qa 的 B／C 對照（9 vs 16 筆）證明設定生效，PR 的 Security job SUCCESS |
| `.gitleaksignore` 刪除項目 | 刪 7 行，全部是 `tasks/v0.6.0`、`tasks/v0.7.0`、`tasks/backlog-cleanup-2026-10` 底下，與回報逐筆列的一致；qa 的 D 情境（無設定檔＋現有 ignore = 7 筆，正好是這 7 筆）證明只刪了因本設定而多餘的項目；非 `tasks/` 的 6 筆保留 |
| 回報、PR 說明不引用 key: value 字串 | 回報與 diff 人工檢視無；qa 另用 regex 掃 PR 說明 0 筆 |
| 寫死設定值、安全問題 | 無；註解 3 行內、只寫理由 |
| 驗收條件 | 四條都有實際輸出佐證（worker 回報＋qa 證據）；回報中「CI 全綠待確認」已由 qa 確認 |

## 非阻擋事項與建議（給 manager）

1. **殘餘風險**：`tasks/` 整個目錄（含進行中的派工單與 `*.meta.json`，不只封存）從此不受 gitleaks 保護，若有人把真密鑰貼進派工單或封存報告，CI 不會擋。對策已在 D-018「影響」寫明（`tasks/` 不可放設定值或密鑰），屬甲方接受的取捨，不需另開 D-編號。
2. **security 發版前審查要知道這個排除**：`.claude/agents/security.md:30` 已要求逐條檢查 `.gitleaks.toml`，流程本身不用改；但 `docs/security/v0.6.0.md:119`、`v0.7.0.md:265` 記的是「`.gitleaks.toml` 不存在、使用預設規則」，v0.8.0 的 security 報告要更新為「存在，extend 預設規則＋排除 `^tasks/`（D-018）」，並抽查 `tasks/` 新增內容沒有真密鑰（例：對 `tasks/` 用不帶設定檔的 `gitleaks dir tasks/` 掃一次，人工判讀結果）。建議 manager 在 v0.8.0 security 派工單的「範圍」寫進這一點。
3. **開發規格同步**：`docs/development-spec.md:38` 寫「誤判寫進 `.gitleaksignore` 等忽略檔並附理由」，字面上涵蓋本變更，但沒提到路徑整體排除。建議 manager（或下一張動到開發規格的單）在同一格補一句「`tasks/` 由 `.gitleaks.toml` 整體排除（D-018）」，讓之後的人知道 `tasks/` 不在掃描範圍。不阻擋本 PR。
