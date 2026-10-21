PASS 4ae31b7

# dashboard-panels qa 第 2 輪（PR #107，head 4ae31b7，驗收測試鎖定 @ 4191a70）

驗收測試自 4191a70 起未被改動（`git diff 4191a70 HEAD --stat -- tests` 為空）。本輪 diff（dfe24da..4ae31b7）只動 `radar.json`、`docs/development-spec.md`。

## 4 個必改

| # | 項目 | 驗證方式 | 結果 |
|---|---|---|---|
| 1 | 面板 6 爭議度推＋噓 < 10 留空 | 種子：A 推6噓6、B 推3噓2、C 只有 arrow；唯讀帳號跑面板 6 SQL | A `爭議度`=0.5；B（5 票）、C（0 票）皆 `None` |
| 2 | 面板 6 情緒套 min_score | 種子 A 預測 positive 0.3；min_score 0.5 與 0.2 各跑一次 | 0.5 -> A「不確定」；0.2 -> A「正面」；B（negative 0.9）「負面」；無推論的 C 維持 `''`（符合鎖定測試） |
| 3 | 面板 5 以 alert_id 去重 | 同一 alert_id 插入兩列（post 型） | 面板 5 只出現 1 列（標題、url、倍數 10、z-score 5 正確） |
| 4 | JOIN 右側 post_id IN 縮小 | 唯讀帳號對面板 2、3、4、5、6 展開後的 SQL 跑 `EXPLAIN indexes = 1` | 見下 |

EXPLAIN indexes = 1 節錄（radar DB 有種子資料，PrimaryKey Keys 皆為 post_id）：

- 面板 2、3：`radar.predictions` PrimaryKey Keys: post_id，Condition: `(post_id in 3-element set)`，Prewhere `post_id IN subquery1`
- 面板 4：右側 `radar.comments_latest` Keys: post_id，Condition: `(post_id in 3-element set)`，Parts 2/5
- 面板 5：右側 `radar.posts_latest` Keys: post_id，Condition: `(post_id in 3-element set)`，Parts 2/5
- 面板 6：右側 `posts_latest`（Parts 2/5）、`comments_latest`（Parts 2/5）、`predictions` 的 Condition 皆為 `post_id in 3-element set`
- 左表 `posts_latest`／`comments_latest`（面板 1、6 內層）以 `commented_at`／`created_at` 過濾，Condition: true，屬 7.25 接受的範圍（review 已註明不在本單處理）

SQL 無 `SETTINGS`（grep 無結果），唯讀帳號全部執行成功。

## 其他驗收

- `make check`：pre-commit 通過，`1110 passed in 3.68s`
- `docker compose --env-file .env -f .worktrees/dashboard-panels/compose.yaml run --rm test`（預設 `-n auto`）：`258 passed in 64.67s`
- 同上加 `pytest tests/integration -n 0 -q`：`258 passed in 132.09s`
- `pytest tests/integration/acceptance/dashboard/test_panels.py -n 0 -q`：`66 passed in 4.92s`
- 連結規則：url 欄以 `startsWith(url, 'https://www.ptt.cc/')` 在 SQL 過濾（面板 4、5、6）
- 7.25 實作註記（`docs/development-spec.md`）已寫入：警示以 alert_id 去重、面板 6 爭議度門檻、情緒「不確定」與空白代表沒有推論、JOIN 右側 post_id IN 縮小；與實測行為一致
- 設定值：radar.json 只引用 datasource uid `radar-clickhouse`，無寫死 host／port／帳密
- PR #107 最新 commit 4ae31b72 的 CI：Check pass（42s）、Integration Test pass（2m7s）、Security pass（29s）
- 已 `down -v`

## 備註（不阻擋）

- 種子資料的 url 都相同，是 seed 設計，非面板問題
- 為了自己放種子資料，我用 `run --rm test python -c` 引用 test_panels.py 的 helper；種子用 uuid 看板名，且 down -v 已清除
- 需 dashboard-integration 驗的項目（board 變數 query 形式、空 url 連結、變數引號展開、無看板時 `board IN ()`）不在本單，review 已列

問題數量：0
