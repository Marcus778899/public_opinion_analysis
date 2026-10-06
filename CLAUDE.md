# CLAUDE.md

AI 協作開發規範。動手前先讀相關文件：

- 設計：[docs/realtime-sentiment-radar-design.md](docs/realtime-sentiment-radar-design.md)（做什麼、為什麼）
- 開發規格：[docs/development-spec.md](docs/development-spec.md)（怎麼做、驗收標準、任務 ID）

回覆與文件一律使用繁體中文；程式碼識別字用英文。

## 指令

```bash
uv sync                                   # 安裝相依套件（含 radar 套件，editable）
uv run pytest tests/unit                  # 單元測試
uv run ruff check --fix . && uv run ruff format .
uv run --env-file .env alembic upgrade head
pre-commit run --all-files
```

## 目錄

- 程式碼都在 `src/radar/`，import 一律寫 `from radar.xxx import ...`
- 每個服務的入口是自己的模組，用 `main()` + `if __name__ == "__main__": main()`，執行方式為 `python -m radar.<module>`
- 測試放 `tests/unit/`、`tests/integration/`，目錄結構對應 `src/radar/`
- PTT HTML 測試資料放 `tests/fixtures/ptt/`

## 開發流程：先刻骨架，審過再實作

每個任務分兩輪，**第一輪結束必須停下來等我確認**，不可直接進入第二輪。

### 第一輪：骨架

1. 建立模組、類別、函式簽名（含完整 type hints）、pydantic / ORM model
2. 函式本體只放 `raise NotImplementedError` 與標記，例如：
   ```python
   def upsert_posts(session: Session, posts: list[RawPost]) -> int:
       # TODO(S1-05): 同批依 post_id 去重，保留 crawled_at 最新的一筆
       raise NotImplementedError
   ```
3. 測試檔一併建立，列出測試案例名稱，先標記 skip：
   ```python
   @pytest.mark.skip(reason="TODO(S1-05)")
   def test_upsert_same_post_twice_in_batch_keeps_latest(): ...
   ```
4. 回報：新增了哪些檔案、介面設計的取捨、有疑問的地方

### 第二輪：實作

- 依確認後的骨架實作，移除對應的 `NotImplementedError` 與 skip
- 實作中發現骨架需要調整，先說明再改

### 標記規則

| 標記 | 用途 |
|---|---|
| `TODO(<任務 ID>)` | 尚未實作，任務 ID 對應開發規格第 6 章，例如 `TODO(S1-04)` |
| `FIXME` | 已知的錯誤，需要修 |
| `HACK` | 暫時的繞道寫法，附上應改成什麼 |
| `NOTE` | 不看註解會誤會的設計理由 |

階段驗收前，`grep -rn "TODO(S<n>-" src tests` 必須沒有結果。

## 程式碼規範

### 註解

- 每段註解最多 3 行；需要更長的說明代表該寫進 docs
- 只寫「為什麼」，不寫「做了什麼」（程式碼本身說明）
- docstring 同樣以 3 行為限，簡單函式不寫

### 風格

- ruff 設定見 `pyproject.toml`（行寬 100），提交前必須通過
- 全部使用 type hints；不用 `Any`，除非接外部無型別資料
- 設定從環境變數讀，不寫死；新增的環境變數同步加到 `.env.example`
- Log 一律用 `from radar.common.log import log`（包裝 loggerhelper），不用 `print`、標準 `logging` 或直接 import loggerhelper；服務入口的 `main()` 第一行呼叫 `setup_logging("<服務名>")`，並加上 `@log.catch(level="CRITICAL")`
- 不新增相依套件，除非先問過我

### 資料與架構約定（違反會造成資料錯誤）

- 時間一律 UTC，PTT 的 `Asia/Taipei` 在 parser 轉換
- `post_id` = `<board>.<PTT 文章檔名>`
- 每張 PG 表只有一個寫入者（設計文件 5.4）；標註、推論結果**不可寫回 `posts`**（會造成 CDC 迴圈）
- 爬蟲不碰 PG；不可同時寫 PG 與 Kafka（雙寫）
- Kafka consumer 處理完才 commit；壞資料送 `dlq`，暫時性錯誤重試
- ORM model（`radar.common.db.models`）只描述 PG 表；Kafka 訊息用 pydantic（`radar.common.schemas`），兩者不混用
- 批次寫入用 SQLAlchemy Core，單筆 CRUD 用 ORM（開發規格 2.4）
- Schema 只透過 Alembic migration 變更；已合併的 migration 不可修改，要改就新增一個

## 測試規範

- **每個新增或修改的函式都要有單元測試**，沒有測試的實作不算完成
- 單元測試不連網路、不連真實 Kafka / PG；需要時用 fake 或 mock
- 整合測試用 testcontainers，放 `tests/integration/`
- **任何測試都不可對真實 PTT 發請求**，只讀 `tests/fixtures/ptt/`
- 測試名稱描述行為：`test_<情境>_<預期結果>`
- 至少涵蓋：正常路徑、邊界值、錯誤輸入；consumer 另需涵蓋重複訊息（冪等）與 DLQ
- 修 bug 先寫一個會失敗的測試重現它，再修

## Git

- 不主動 commit 或 push，除非我要求
- 分支：`feat/s<階段>-<簡述>`、`fix/<簡述>`，從 `develop` 開，合回 `develop`
- Commit 使用 Conventional Commits：`feat(crawler): ...`、`test(ingest): ...`
- 不提交 `.env`、爬下來的資料、模型檔

## 文件同步

- 改動資料流、表、topic、訊息格式時，先更新設計文件或開發規格，再改程式
- 發現文件與實作不一致時，指出來，不要自行決定以哪邊為準
