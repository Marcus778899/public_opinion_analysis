APPROVE 4ae31b7

# dashboard-panels review 第 2 輪（PR #107，head 4ae31b7，驗收測試鎖定 @ 4191a70）

上一輪 REQUEST_CHANGES dfe24da 的 4 個必改都已處理；本輪重看整個 PR（不只 dfe24da..4ae31b7 的差異），沒有阻擋問題。

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 改動範圍 | PR 檔案：`radar.json`、`.gitkeep`（刪）、`docs/development-spec.md`，加上 qa 的 `test_panels.py`；本輪（dfe24da..4ae31b7）只動 `radar.json`、spec。沒碰禁區（migration、provisioning、compose、`src/`、`scripts/`、`.claude/`、`contracts/`） |
| 驗收測試未被改 | `git diff 4191a70 4ae31b7 --stat -- tests` 為空 |
| 必改 1 面板 6 爭議度 | `if(v.push + v.boo >= 10, round(...), NULL)`，與 7.23、面板 4 同門檻；LEFT JOIN 沒對到時 push、boo 為 0 也落到 NULL。通過 |
| 必改 2 面板 6 情緒 | `multiIf` 依序：沒有推論 → `''`、`score < min_score` → 不確定、再分三類；與面板 2、bot `sentiment_text` 一致。通過 |
| 必改 3 面板 5 去重 | 先在 `alerts` 以 `ORDER BY created_at DESC LIMIT 1 BY alert_id` 去重再 JOIN；沒用 `SETTINGS`。通過（qa 以重複 alert_id 實測只出 1 列） |
| 必改 4 JOIN 右邊縮小 | 面板 2、3、4、5、6 的右邊都以 `post_id IN (子查詢)` 縮小；qa 附唯讀帳號 `EXPLAIN indexes = 1`：`predictions`、`comments_latest`、`posts_latest` 的 PrimaryKey 條件為 `post_id in N-element set`。面板 1 與面板 6 內層、IN 子查詢本身以 `commented_at` 全表掃，屬 7.25「慢了再加 MV」接受的範圍 |
| 順手修 | 面板 4 `ORDER BY` 加第二鍵 `p.post_id`；面板 6 文章改 LEFT JOIN、標題退回 `post_id`（`p.post_id = ''` 判斷依 `join_use_nulls=0` 預設，唯讀帳號無法改設定，驗收測試以同帳號跑過） |
| 面板 1～6 對 7.25 | 來源、類型、時間範圍、看板變數、面板 3 只算有推論且以台北時間分日、面板 5 不跟時間範圍與看板變數，皆符合 |
| readonly=1 | `grep SETTINGS\|SET \|GLOBAL radar.json` 無結果；只用 SELECT、FINAL、JOIN、IN、LIMIT BY、一般函式 |
| 連結過濾 | 面板 4、5、6 的 `url` 以 `startsWith(url, 'https://www.ptt.cc/')` 在 SQL 過濾、欄位隱藏、data link 只引用它；沒有 Text／HTML 面板。通過 |
| 設定值 | 只引用 datasource uid `radar-clickhouse`；沒有寫死 host、port、帳密；dashboard `editable: false`、uid `radar`，與 provisioning `allowUiUpdates: false` 一致 |
| `TODO(dashboard-panels)` | `grep -rn` 於 src、tests、infra、docs 無結果 |
| 7.25 回寫 | 實作註記涵蓋：連結過濾、寬表欄、`min_score` 轉型、警示去重、面板 6 爭議度門檻與情緒、空白代表沒有推論、右邊 `post_id IN`；重複欄位清單已刪；進度表標 `dashboard-panels` 完成。與實作一致 |
| 驗證 | qa（PASS 4ae31b7）：`make check` 1110 passed；`run --rm test` 258 passed（含 `-n 0`）；`test_panels.py` 66 passed；已 down -v。PR #107 @ 4ae31b7 CI：Check、Integration Test、Security 皆 SUCCESS（`gh pr view 107`） |

## 不阻擋（可順手，或之後的單處理）

- 面板 6（`radar.json:284`）內層 `ORDER BY new_comments DESC LIMIT 20` 同分時取哪 20 篇不固定，外層排序同理；可加第二鍵 `post_id`
- 必改 1～3 的行為（爭議度留空、情緒「不確定」、警示去重）只有 qa 手動種子驗證，鎖定的 `test_panels.py` 沒有自動測試；建議 dashboard-integration 的 qa 在 `tests/integration/dashboard/` 補上，避免之後改 JSON 時回歸

## 給 dashboard-integration 派工單（建議 manager 寫進「驗收條件」）

worker 的兩點都要寫明，只有走 `/api/ds/query`／實際畫面才驗得到：

| 項目 | 通過條件 |
|---|---|
| board 變數 query 物件形式（`{query, rawSql, editorType, format}`） | provisioning 後 `/api/dashboards/uid/radar` 讀回的變數能列出種子看板；以 plugin 4.23.0 實際展開 `$board`（含 All、單選、多選）無錯誤 |
| 空字串 url 的標題連結 | 截圖證據：url 為空的列點擊不會離開到外部網址（停在原頁或無動作皆可）；`https://www.ptt.cc/` 的列開新分頁到原文 |
| `$board`、`$min_score` 的展開與引號 | plugin 實際展開的 SQL 中，值含 `'` 時被跳脫或查詢失敗，不會改變查詢結構（唯讀帳號限縮了影響，但仍要確認）；`$min_score` 非數字時面板不報錯 |
| 沒有任何看板時（`posts_latest` 為空） | `board IN ()` 的展開不讓面板報錯，或記錄為已知限制 |

## 契約問題（不屬決策分級四類，architect 自行決定）

- 上一輪判定維持：面板 6 沒有推論時顯示空白（照鎖定測試），已寫進 7.25 實作註記

問題數量：0（阻擋）＋ 2（不阻擋）
