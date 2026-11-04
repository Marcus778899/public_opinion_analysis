# 派工單 comment-time-recrawl

- **類型**：chore
- **負責**：backend
- **目標**：依 D-033，對已入庫且 `commented_at` 落在未來的推文所屬文章（約 55 篇）觸發一次重爬，由爬蟲以 PR #211 的新規則覆寫
- **背景**：#179 修正只影響新爬到的推文；開發 PG 目前約 251 則落在未來。新規則需在跑著的爬蟲 image 內才生效（manager 會在派工前重建並重啟 crawler，見執行資訊下方追加）
- **設計依據**：D-033；`docs/development-spec.md` 7.12（重爬任務）、7.15（推文同步）、2.1；單一寫入者規則（CLAUDE.md「資料與架構約定」）——不可直接 UPDATE PG／ClickHouse，只能透過既有的爬蟲任務流程讓爬蟲重爬
- **相依**：無
- **負責檔案**：
  - `tools/recrawl_posts.py`（若既有機制不夠才新增：讀 post_id 清單、送出與 scheduler 相同格式的重爬任務）
  - `tests/unit/tools/test_recrawl_posts.py`
  - `reports/comment-time-recrawl.json`
- **禁區**：不改 collector、scheduler、ingest 程式；不直接寫 PG／ClickHouse；不對看板做全量重爬
- **驗收測試**：無
- **驗收條件**：
  - [ ] 先查出目標 post_id 清單（唯讀查詢，附查詢與筆數）
  - [ ] 用既有機制或新工具送出重爬任務；工具有單元測試（不連真實服務）
  - [ ] 實際執行後，附重跑同一查詢的結果：落在未來的推文筆數降到 0（推不回的變 NULL，筆數另列）
  - [ ] `make check` 通過
- **驗證指令**：回報附查詢前後輸出；`uv run pytest tests/unit/tools/test_recrawl_posts.py`；`make check`
- **回報檔**：`reports/comment-time-recrawl.json`

## 執行資訊（task.py 產生）

- Issue：#218
- 分支：`chore/comment-time-recrawl`（從 develop 開出）
- 工作目錄：`.worktrees/comment-time-recrawl`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

manager：新測試目錄需要 `__init__.py`（與其他測試目錄一致），加入負責範圍。剩下 10 則（3 篇已刪文，重爬只會標記刪除、不同步推文）接受留著，不另處理（直接改資料庫違反單一寫入者規則）。更新後的完整清單：

- **負責檔案**：
  - `tools/recrawl_posts.py`
  - `tests/unit/tools/test_recrawl_posts.py`
  - `tests/unit/tools/__init__.py`
  - `reports/comment-time-recrawl.json`
