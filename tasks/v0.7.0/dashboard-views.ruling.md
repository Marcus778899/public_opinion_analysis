TEST_OK 0cb8190

# 仲裁：dashboard-views 驗收測試

依據：開發規格 7.25「測試環境」查詢的 DB 一列、7.26「平行執行的隔離」表；驗收測試 `tests/integration/acceptance/dashboard/test_views.py` @ ecb0cc9；worker 回報 `reports/dashboard-views.json` 的 disputes。只讀程式碼判定，沒有重跑 compose：失敗原因從程式碼就能確定（見下方第 4 列）。

## 判定

| 測試 | 契約條文 | 判定與理由 |
|---|---|---|
| `test_views.py` 全部（種子資料寫在 `radar` DB、沒有 `xdist_group`） | 7.25：「dashboard 的驗收與整合測試一律在 `radar` DB 放種子資料、以唯讀帳號查…種子資料的看板名稱帶 uuid、斷言只看自己的看板，不需 `xdist_group`」 | 符合。每個測試的看板都由 `_board()` 帶 uuid；`_votes` 用 `board` 過濾、`_sentiments` 用 `post_id IN (...)` 過濾；system 表的查詢有限定 `database='radar'` 與表名稱。沒有用 Kafka topic，也沒有斷言整張表 |
| 同上，對照 7.26 的分組規則 | 7.26：「新測試用到固定名稱 topic 且斷言整張表／整個 topic 時才需要標」 | 符合。test_views 直接 INSERT，沒有用 topic，也沒有斷言整張表，所以照規則不用標 group。如果改成加入 `shared_radar_db` 來避開這次失敗，就違反 7.25「不需 `xdist_group`」；後面的 `test_panels.py`、`tests/integration/dashboard/` 也會在 `radar` DB 放種子資料，加 group 只能擋這一次 |
| `tests/integration/cdc/test_clickhouse_migrations.py::test_json_topic_rows_land_in_target_tables`（不是驗收測試） | 7.26 `radar` DB 一列：「只有 `cdc/test_clickhouse_migrations.py` 用…它的斷言只看自己的 `unit_key`」 | **問題在這裡**：這個測試跟 7.26 寫的不一樣。只有 alerts 依 `unit_key` 過濾；labels（`_wait_rows(ch, "labels", 2)` 與 `SELECT … FROM labels`）和 predictions（`_wait_rows(ch, "predictions", 1)` 與 `SELECT … FROM predictions`）都是查整張表。所以在 `radar` DB 合法寫入資料的其他測試一跑，它就會失敗 |
| 同上，失敗機制 | — | test_views 在別的 xdist worker 寫入 12 列 predictions，`_wait_rows(…, 1)` 會在 Kafka 訊息落表之前就提早成立，接著整張表的斷言就多出 12 列。這是 0005 之前就存在的潛在缺陷，跟 0005 的實作無關 |

## 該怎麼修（給 manager）

| 項目 | 由誰 | 改哪裡 | 怎麼改 |
|---|---|---|---|
| cdc 測試的斷言改成只看自己的 post_id | backend（建議直接把這個檔加進 dashboard-views 的負責檔案：它不是鎖定的驗收測試，而且它卡住本單 CI；另開 `fix/` 單也可以，但本單要等它合併） | `tests/integration/cdc/test_clickhouse_migrations.py` 的 `test_json_topic_rows_land_in_target_tables` | `_wait_rows` 改成 `"labels WHERE post_id = 'Stock.M.1.A.1'"`, 2 與 `"predictions WHERE post_id = 'Stock.M.1.A.1'"`, 1；兩個 `SELECT … FROM labels`／`FROM predictions` 加上同樣的 `WHERE post_id = 'Stock.M.1.A.1'`；期望值不變 |
| 7.26 文字跟著更新 | 同一張單（`docs/development-spec.md` 已經是 dashboard-views 的負責檔案） | 開發規格 7.26 平行隔離表的 `radar` DB 一列 | 「它的斷言只看自己的 `unit_key`」改成「它的斷言只看自己的 `post_id`／`unit_key`；`radar` DB 的資料表可能有其他測試的種子資料（7.25），任何測試都不可以斷言整張表」。7.25 不用改 |

修完以後照原本的驗證指令重跑 `docker compose --env-file .env -f .worktrees/dashboard-views/compose.yaml run --rm test`，要全部通過。test_views 和 0005 都不用改。

## 契約問題

- 7.26 寫「它的斷言只看自己的 `unit_key`」，但實作只做到 alerts，文件和實作不一致（處理方式見上表第 2 列）。這不屬於決策分級的四類，不用開 D-編號。
