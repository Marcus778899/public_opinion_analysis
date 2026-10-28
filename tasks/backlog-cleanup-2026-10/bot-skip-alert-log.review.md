APPROVE bc5ec03

# Review PR #133（bot-skip-alert-log）

head `bc5ec0388fa2`；變更：`src/radar/bot/repository.py`、`tests/unit/bot/test_repository.py`（皆在追加後的負責檔案內）。

## 檢查項目

| 項目 | 結果 | 依據 |
|---|---|---|
| 送給誰、略過誰與修改前一致 | 一致 | 原條件 `(無 chat_settings 列 OR 開關 IS TRUE) AND NOT muted(僅 post)`；新版取回 `(chat_id, 開關, muted)` 後由 `filter_recipients` 過濾：`enabled is False` 略過、`muted` 略過，其餘保留。`post_alerts`／`board_alerts` 為 NOT NULL（開發規格 S6-02），`None` 只代表沒有列，等同原本的 `chat_id IS NULL`；board 警示 `muted = literal(False)`，與原本 board 不檢查 mute 相同；`ORDER BY chat_id` 保留 |
| 仍是一次查詢 | 是 | `exists()` 放在 select 欄位內的 correlated subquery，沒有逐 chat 查 PG。correlation 由既有整合測試證明：`test_recipients_filters_subscription_type_and_mute` 中 chat 4 mute 後 post 結果為 `[1, 3]`（沒 correlate 會變 `[]`），測試未修改，CI Integration Test pass |
| 不寫 PG、不改 schema | 是 | 只改讀取查詢 |
| log 規範（CLAUDE.md） | 符合 | `from radar.common.log import log`；INFO；`%` 參數與同模組既有寫法一致；含 alert、unit_type/unit_key、chat、原因；不含 token 或個資以外的新資訊（chat_id 既有 log 已記） |
| 正常送出行為與 log 不變 | 是 | `notify.py`、`main.py` 未改；`recipients` 回傳型別不變 |
| 單元測試覆蓋驗收條件 | 有 | disabled 略過有 log、muted 略過有 log、未略過無 log、空輸入；`filter_recipients` 每個分支都有測到 |
| 寫死設定、安全 | 無問題 | 參數綁定，無字串拼接 |
| CI | Check、Integration Test pass；Security fail 為 develop 既有 gitleaks 誤判（#134 已修），與本 PR 無關 |

## 文件同步

開發規格 §S6「推送對象」（docs/development-spec.md 約 994 行）寫「`recipients(alert)` 一個查詢——訂閱該看板、沒關掉這種警示、文章警示另排除不再通知」，結果語意與「一個查詢」仍成立，不算與實作不一致，不阻擋。

建議（非阻擋，worker 的負責檔案不含 docs）：manager 另以 docs 提交在該條後補一句「被 chat_settings 關閉或不再通知略過時，每個 chat 記一行 INFO（原因 `chat_settings disabled`／`post muted`），過濾在 Python 端」。

## 非阻擋觀察

- muted 略過也記 log，比派工單字面「通知設定」寬，但屬同類資訊、有助排查，可接受。
- 同時關閉且 mute 時只記 `chat_settings disabled`，worker 已在回報說明。

問題數量：0
