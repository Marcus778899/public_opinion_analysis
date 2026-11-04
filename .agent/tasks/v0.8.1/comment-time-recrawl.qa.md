PASS 14c8dbd

## 證據
- 工具只送 Kafka：tools/recrawl_posts.py 只 import JsonProducer／make_post_task，無 PG／ClickHouse 引用；無寫死的 port／網址（PTT_BASE_URL 來自 radar.common.ids，Kafka 設定走 get_kafka_settings）。
- `pytest tests/unit/tools`（PYTHONPATH=worktree src）：6 passed。涵蓋正常（build/send/read_ids）、空清單（build_tasks 空）、錯誤輸入（格式錯誤丟 ValueError、空白與重複行）；用 MagicMock producer，不連服務。
- `pytest tests/unit -n auto`：1466 passed。ruff check／format --check：通過。無 TODO(comment-time-recrawl)。
- 唯讀重跑查詢（開發 PG）`select count(*), count(distinct post_id) from comments where commented_at > now();` -> `10|3`
- 分組：Gossiping.M.1792476838.A.1A9|1|is_deleted=t；Gossiping.M.1792490846.A.0B3|4|t；Gossiping.M.1793178844.A.353|5|t -> 共 10 則、3 篇，全為已刪文，與回報一致；追加已接受，不算 FAIL。

## 備註（非 FAIL）
- send_tasks 無獨立的空清單測試（main 對空清單直接 SystemExit，未測）；影響小。
- 回報自述曾把工具複製進 ingest 容器 /tmp，容器重建即消失。
- 未單獨跑 pre-commit（make check 的一部分）；以 ruff 與 unit 全跑代替。
