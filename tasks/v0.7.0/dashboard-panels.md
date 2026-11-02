# 派工單 dashboard-panels

- **類型**：feat
- **負責**：backend
- **目標**：寫 Grafana dashboard JSON（radar.json），含 7.25 的 6 個面板與 board、min_score 兩個變數，由 provisioning 載入（開發規格 7.25 派工順序 3）
- **背景**：dashboard-grafana-infra、dashboard-views 已合併（PR #100、#105）。architect review 提醒：唯讀帳號 readonly=1，面板 SQL 不可用 SETTINGS；plugin 另外帶的設定只在 dashboard-integration 驗得到。測試只看自己的看板（7.26：任何測試都不可斷言整張表）
- **設計依據**：`docs/development-spec.md` 7.25（面板表、變數、時間巨集、連結規則、測試環境、派工順序 3）、7.26；`docs/realtime-sentiment-radar-design.md` 6.3；D-014
- **相依**：dashboard-views（已合併）
- **負責檔案**：
  - `infra/grafana/dashboards/radar.json`
  - `infra/grafana/dashboards/.gitkeep`
  - `docs/development-spec.md`
- **禁區**：不改 migration、provisioning、compose、`src/`；面板 SQL 不用 SETTINGS、只用 7.25 列的巨集與變數；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：
  - `tests/integration/acceptance/dashboard/test_panels.py`
- **驗收條件**：
  - [ ] 驗收測試全過：每個面板的 SQL 代換後以唯讀帳號在 radar DB 執行，結果符合種子資料
  - [ ] `make check` 通過；`docker compose --env-file .env -f .worktrees/dashboard-panels/compose.yaml run --rm test` 全過並附輸出；交單前 down -v
  - [ ] 表格標題連結只用 posts_latest.url 且限 https://www.ptt.cc/ 開頭
  - [ ] 開發規格 7.25 標實作完成；順手刪掉 7.25 重複的欄位清單那行（review 備註）
  - [ ] PR 的 CI 全綠
- **驗證指令**：`make check`；`docker compose --env-file .env -f .worktrees/dashboard-panels/compose.yaml run --rm test`
- **回報檔**：`reports/dashboard-panels.json`

## 執行資訊（task.py 產生）

- Issue：#106
- 分支：`feat/dashboard-panels`（從 develop 開出）
- 工作目錄：`.worktrees/dashboard-panels`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-21

### reports/dashboard-panels.review.md

REQUEST_CHANGES dfe24da

# dashboard-panels review（PR #107，head dfe24da，驗收測試鎖定 @ 4191a70）

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 改動範圍 | 只有 `radar.json`、`.gitkeep`（刪）、`docs/development-spec.md`，加上 qa 的 `test_panels.py`（4191a70）；沒碰禁區 |
| 6 個面板對 7.25 的來源、類型、時間範圍、看板變數 | 面板 1～5 符合；面板 6 有兩處與 7.23 不一致（問題 1、2） |
| 與 bot 邏輯一致（7.23、`bot/views.py` 的 `controversy`、`sentiment_text`） | 面板 4 的門檻 ≥ 10、面板 2 的「不確定」（`score < min_score`）、「尚無」一致；面板 3 不套 min_score，與 bot 看板概況（`SENTIMENT_QUERY`）一致；面板 6 不一致 |
| readonly=1 | 沒有 `SETTINGS`、`SET`、暫存表、`GLOBAL`；只用 SELECT、`FINAL`、JOIN、`IN (子查詢)`、一般函式，唯讀帳號可執行（驗收測試以唯讀帳號跑過）。plugin 帶的設定仍只能在 dashboard-integration 驗 |
| 效能（每天數千篇） | 時間範圍只過濾左表；JOIN 右邊的 view 每次都算整張表（問題 4） |
| 連結過濾 | `startsWith(url, 'https://www.ptt.cc/')`（含結尾斜線）在 SQL 端過濾，`ptt.cc.evil`、`@` 繞法都過不了（host 在第一個 `/` 前就固定）；data link 只引用已過濾的 `url` 欄，`url` 欄隱藏；標題在 table 內以純文字顯示，沒有 Text／HTML 面板。通過 |
| 設定值 | 沒有寫死 host、port、帳密；datasource 只引用 uid `radar-clickhouse` |
| 7.25 回寫 | 實作註記已加、重複欄位清單已刪；修完問題 1～4 後要同步更新該註記 |

## 要修改的問題

1. `infra/grafana/dashboards/radar.json:284`（面板 6 `爭議度`）— 推＋噓 < 10 時仍算出數值，沒有推噓時顯示 0；7.23「推＋噓 < 10 時不顯示」、bot `views.controversy` 回 `None`，面板 4 也以 10 為門檻，同一張 dashboard 兩種定義 — 改成 `if(v.push + v.boo >= 10, round(v.boo / (v.push + v.boo), 2), NULL)`（表格顯示空白）。不影響 `test_hot_*`（只斷言新增推文、推、噓）
2. `infra/grafana/dashboards/radar.json:284`（面板 6 `情緒`）— 沒套 `min_score`：分數 0.3 的推論顯示「正面」，同一篇在面板 2 卻算「不確定」；bot `sentiment_text` 低於門檻顯示「不確定」 — `multiIf` 在判斷 polarity 前加 `s.score < toFloat64OrDefault('$min_score', 0.5), '不確定'`（`s.post_id = ''` 仍放第一個）。沒有推論維持空字串：鎖定的 `test_hot_ranks_by_new_comments_in_range_with_votes_and_sentiment` 不允許 row_y 出現「尚無」，見下方「契約問題」
3. `infra/grafana/dashboards/radar.json:348`（面板 5）— `alerts` 是 Kafka engine → MergeTree，ClickHouse 消費是 at-least-once，重送時同一個 `alert_id` 會有多列；bot 看板概況已用 `uniqExact(alert_id)` 防這件事，面板會列出重複警示 — 在 `alerts` 端先去重，例如 `FROM (SELECT * FROM alerts WHERE created_at >= now64(6) - INTERVAL 24 HOUR ORDER BY created_at DESC LIMIT 1 BY alert_id) AS a`（或 `GROUP BY alert_id` 配 `any()`）；不可用 `SETTINGS`
4. `infra/grafana/dashboards/radar.json:130、176、220、284、348`（面板 2～6 的 JOIN 右邊）— `post_votes`、`post_sentiment_latest` 是一般 view，`posts_latest FINAL` 在面板 5 也整張放在右邊；ClickHouse 的 hash join 會先把右邊整個算完，時間範圍只過濾左表。表沒有 TTL（0001～0003），每分鐘自動更新 × 每個面板都對整張 `comments_latest FINAL`／`predictions` 聚合，資料累積幾個月後會撞上唯讀帳號的 `max_execution_time` 60 秒與 `max_memory_usage` — 右邊一律先用 `post_id IN (…)` 縮到左邊會用到的文章（`post_id` 是 `comments_latest`、`predictions`、`posts_latest` 排序鍵的第一欄，走主鍵索引）：
   - 面板 2、3、4：`(SELECT … FROM post_sentiment_latest／post_votes WHERE post_id IN (SELECT post_id FROM posts_latest WHERE $__timeFilter_ms(created_at) AND board IN ($board)))`（IN 的子查詢不需 FINAL，取到超集即可）
   - 面板 6：右邊的 `posts_latest FINAL`、`post_votes`、`post_sentiment_latest` 以 `post_id IN (SELECT post_id FROM comments_latest WHERE is_deleted = 0 AND $__timeFilter_ms(commented_at) AND board IN ($board))` 縮小（或以 `WITH` 取前 20 的 post_id）
   - 面板 5：`LEFT JOIN (SELECT post_id, title, url FROM posts_latest FINAL WHERE post_id IN (SELECT unit_key FROM alerts WHERE unit_type = 'post' AND created_at >= now64(6) - INTERVAL 24 HOUR)) AS p`
   - 驗證：回報附唯讀帳號跑 `EXPLAIN indexes = 1 <展開後的 SQL>` 的輸出，`comments_latest`、`predictions`、`posts_latest` 的 PrimaryKey 條件要出現 `post_id`；驗收測試照樣全過
   - 面板 1 與面板 6 內層對 `comments_latest FINAL` 以 `commented_at`（非排序鍵）過濾仍是全表掃，這是 7.25「先不加 MV，慢了再加」接受的範圍，不在本單處理

修完後更新 7.25 的實作註記（面板 6 的爭議度門檻、情緒「不確定」與空白代表沒有推論、警示以 `alert_id` 去重、右邊以 `post_id IN` 縮小）。

## 不阻擋（可順手）

- 面板 4（:220）同分時順序不定：`ORDER BY` 加第二鍵（例：`v.push + v.boo DESC, p.post_id`），bot `CONTROVERSIAL_QUERY` 也以 `post_id` 當第二鍵
- 面板 6（:284）`INNER JOIN posts_latest`：推文先於文章進 ClickHouse 時（兩個 CDC topic 沒有順序保證），前 20 會少列；可改 LEFT JOIN、標題退回 `post_id`

## 給 dashboard-integration 派工單（建議 manager 寫進「驗收條件」）

worker 的兩點都要寫明，只有走 `/api/ds/query`／實際畫面才驗得到：

| 項目 | 通過條件 |
|---|---|
| board 變數 query 物件形式（`{query, rawSql, editorType, format}`） | provisioning 後 `/api/dashboards/uid/radar` 讀回的變數能列出種子看板；以 plugin 4.23.0 實際展開 `$board`（含 All、單選、多選）無錯誤 |
| 空字串 url 的標題連結 | 截圖證據：url 為空的列點擊不會離開到外部網址（停在原頁或無動作皆可）；`https://www.ptt.cc/` 的列開新分頁到原文 |
| `$board`、`$min_score` 的展開與引號 | plugin 實際展開的 SQL 中，值含 `'` 時被跳脫或查詢失敗，不會改變查詢結構（唯讀帳號限縮了影響，但仍要確認）；`$min_score` 非數字時面板不報錯 |
| 沒有任何看板時（`posts_latest` 為空） | `board IN ()` 的展開不讓面板報錯，或記錄為已知限制 |

## 契約問題（不屬決策分級四類，architect 自行決定）

- 7.25 面板 6 只寫「附…文章情緒」，沒定沒有推論時顯示什麼；鎖定的驗收測試要求這種列不出現任何類別字（含「尚無」），與 bot 顯示「尚無」不同。判定：照測試，空白即代表沒有推論，寫進 7.25 實作註記即可，不改測試

問題數量：4（阻擋）＋ 2（不阻擋）

manager 補充：review「給 dashboard-integration 的事項」不用在本單處理（會寫進那張派工單）；「建議」可順手修。交單時附 EXPLAIN indexes = 1 的輸出、重跑 run --rm test 全過（做完 down -v）。
