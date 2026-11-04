APPROVE 14c8dbd

## 檢查範圍

PR #220（`chore/comment-time-recrawl`），對照派工單 `tasks/comment-time-recrawl.md`（含 2026-10-29 追加）、D-006、D-033、開發規格 7.12、CLAUDE.md「資料與架構約定」。

| 項目 | 結果 | 依據 |
|---|---|---|
| 任務格式與 scheduler 一致 | 符合 | `build_tasks` 呼叫的 `radar.common.tasks.make_post_task(post_id, board, url, CrawlReason.RECRAWL, now)` 與 `src/radar/collector/recrawl.py:127-128` 相同；送到 `names.CRAWL_TASKS`、key 是 `task.kafka_key()`（= post_id），不指定 partition，與 scheduler 的文章重爬相同（同一篇落在同一個 partition，7.12 的 LRU 去重照常運作） |
| URL | 符合 | `{PTT_BASE_URL}/bbs/{board}/{filename}.html`，與 `ml/labeling/cross_check.py:86`、`bot/views.py:76` 同一種寫法；`split_post_id` 先驗證 post_id 格式，格式不對整批不送 |
| `created_at` | 符合 | 取送出當下的時間，爬蟲 `crawler.py:120` 的 `fetched_since` 不會把它當成重複任務略過（7.12） |
| 單一寫入者 | 符合 | 工具只 produce `crawl.tasks`，沒有 import PG／ClickHouse；推文由爬蟲→ingest 既有流程覆寫。`crawl.tasks` 原本就有 scheduler 與 API 兩個生產者，多一個營運工具不違反「每張 PG 表只有一個寫入者」 |
| D-006 放置 | 符合 | 放 `tools/`，不在 `scripts/`；入口 `main()` 有 `@log.catch(level="CRITICAL")`、第一行 `setup_logging`，寫法同 `tools/seed_boards.py` |
| 設定 | 符合 | Kafka 設定走 `get_kafka_settings()`，沒有寫死 port／網址；沒有新環境變數 |
| 負責檔案 | 符合 | 只改 `tools/recrawl_posts.py`、`tests/unit/tools/test_recrawl_posts.py`、`tests/unit/tools/__init__.py`（追加已納入） |
| 單元測試 | 符合 | 6 個測試涵蓋正常、空清單、格式錯誤、空白與重複行、送出 topic／key／flush；producer 用 MagicMock，不連服務 |
| 驗收條件「降到 0」 | 依追加接受 | 剩 10 則／3 篇皆 `is_deleted=t`（404 只標記刪除），manager 追加已接受留著；qa 重跑查詢 `10|3` 與回報一致 |

## 實際執行（PYTHONPATH 固定為 worktree 的 src）

- `PYTHONPATH=$PWD/src uv run --frozen python -c "import radar; print(radar.__file__)"` → `.worktrees/comment-time-recrawl/src/radar/__init__.py`
- `PYTHONPATH=$PWD/src uv run --frozen pytest tests/unit/tools -q` → `6 passed`
- `uv run --frozen ruff check tools tests/unit/tools` → `All checks passed!`；`ruff format --check` → `7 files already formatted`
- `grep -rn "TODO(comment-time-recrawl)" src tests tools` → 無結果
- CI：Security pass；Check、Integration Test 在 review 時仍 pending（合併前看結果）

## 不擋合併的備註

1. `.coverage-exempt` 對 `tools/*` 的理由是「只把 env 與檔案路徑接到 radar.common 裡已有單元測試的函式」；這支工具把解析與組任務的邏輯放在 `tools/` 裡，覆蓋率關卡量不到。已有單元測試補上，一次性營運工具可以接受；之後若要重用，`parse_post_ids`／`build_tasks` 可搬到 `radar.common.tasks`。
2. `tests/unit/tools/` 不對應 `src/radar/` 的目錄結構（CLAUDE.md 目錄規則）；tools 本來就在 `src` 外，manager 追加已核可，沒有更好的位置。
3. 回報 `files_changed` 漏列 `tests/unit/tools/__init__.py`。
4. 流程問題（不在 PR 內）：worker 曾用 `docker compose cp` 把工具複製進跑著的 ingest 容器 `/tmp/recrawl_posts.py` 並 `exec` 執行。容器內殘留這個檔，manager 可在下次重建 ingest 時清掉；之後的營運工具應以 `docker compose run --rm` 或主機端執行，不改跑著的容器。
