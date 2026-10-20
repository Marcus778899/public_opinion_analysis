# CLAUDE.md（團隊共用規範）

所有 agent 啟動時都會讀這份。只放永遠成立的規則，越短越好；情境知識放 skills。

@BOARD.md

## 團隊規則

- 布告欄（BOARD.md）上的「已定案決策」不可推翻；與之矛盾時停下來回報 manager
- 只有 manager 可以改 BOARD.md（透過 `scripts/board.py`）、README.md、docs/decisions.md
- 每件工作都有派工單 `tasks/<task_id>.md`（task_id 是有意義的名稱，例 `todo-create-api`）；只在派工單的工作目錄 `.worktrees/<task_id>` 修改「負責檔案」；主目錄只寫自己角色規定的檔（回報與證據 `reports/`，uat、researcher、security 各自的 `docs/` 子目錄），其他一律不碰；過去階段的派工單封存在 `tasks/<tag>/`
- 分支：`main` ← `develop` ← `feat/`、`fix/`、`chore/`…；主目錄永遠停在 develop；不可直接 git push、merge、rebase、切換分支，一律透過 `scripts/`
- 需要甲方決定的事寫成 D-編號，集中在 `docs/decisions.md`；其他文件只引用編號
- 決策分級：只有這四類開 D-編號問甲方——①範圍（做不做、做多少）②成本與外部依賴（付費服務、新技術棧或套件）③品牌與對外語氣（品牌色、名稱、文案語氣）④不可逆或有風險（刪資料、權限、資料遷移、安全與法規）。其他可逆、在範圍內的細節（互動方式、版面、元件、欄位排序、命名…）由負責角色自己決定，寫進設計或 UI 規格的「自行決定」表，甲方核可設計時一起看
- 設定值（port、domain、token…）只放 `.env`；文件與程式只寫變數名稱；不可讀 `.env`
- 文件精簡：同一件事只寫一次，其他地方引用
- 「完成」必須附實際執行的驗證指令與輸出；沒跑過不算完成
- 回報格式依 `contracts/report.schema.json`（做派工單的角色都要寫）
- Bash 在 sandbox 裡；docker 只能直接下 `docker compose …`（唯一在 sandbox 外的例外），不要包在 make、script 裡或跟 `cd`、`&&` 寫在同一個指令

## 專案規範（PTT 即時輿情雷達）

動手前先讀相關文件：

- 設計：[docs/realtime-sentiment-radar-design.md](docs/realtime-sentiment-radar-design.md)（做什麼、為什麼）
- 開發規格：[docs/development-spec.md](docs/development-spec.md)（怎麼做、各階段範圍與驗收標準；進度看布告欄，見 D-004）

回覆與文件一律使用繁體中文；程式碼識別字用英文。

### 指令

```bash
uv sync                                   # 安裝相依套件（含 radar 套件，editable）
uv run pytest tests/unit                  # 單元測試
uv run ruff check --fix . && uv run ruff format .
pre-commit run --all-files
```

Makefile 裡碰 docker 或 `.env` 的目標（`make up`、`up-app`、`migrate`、`topics`、`e2e-up`…）在 sandbox 裡會失敗：
agent 改成直接下 `docker compose -f infra/docker-compose.yaml --env-file .env …`（對應寫法見 Makefile）。
開發與 e2e 共用容器名稱，不能同時運作（#41）；e2e 只用假 PTT（`infra/docker-compose.e2e.yaml`）。
整合測試：agent 下 `docker compose --env-file .env -f .worktrees/<task_id>/compose.yaml run --rm test`，做完用同一條指令把 `run --rm test` 換成 `down -v` 釋放記憶體；這組容器與開發／e2e（專案 `radar`）互不相干，可以同時運作。`make test-int` 也包 docker，同樣在 sandbox 裡會失敗。

### 目錄

- 程式碼都在 `src/radar/`，import 一律寫 `from radar.xxx import ...`
- 每個服務的入口是自己的模組，用 `main()` + `if __name__ == "__main__": main()`，執行方式為 `python -m radar.<module>`
- 營運腳本（建 topic、ClickHouse migration、註冊 connector、seed）放 `tools/`；`scripts/` 是流程腳本，不放專案程式（D-006）
- 測試放 `tests/unit/`、`tests/integration/`，目錄結構對應 `src/radar/`；驗收測試目錄由設計指定
- PTT HTML 測試資料放 `tests/fixtures/ptt/`

### 標記規則

| 標記 | 用途 |
|---|---|
| `TODO(<task_id>)` | 骨架中尚未實作，`<task_id>` 是派工單名稱；沒有派工單的修正用 `TODO(#<issue>)` |
| `FIXME` | 已知的錯誤，需要修 |
| `HACK` | 暫時的繞道寫法，附上應改成什麼 |
| `NOTE` | 不看註解會誤會的設計理由 |

一張單合併前，`grep -rn "TODO(<task_id>)" src tests` 必須沒有結果。

### 程式碼規範

- 註解每段最多 3 行，只寫「為什麼」；需要更長的說明代表該寫進 docs。docstring 同樣以 3 行為限，簡單函式不寫
- ruff 設定見 `pyproject.toml`（行寬 100），提交前必須通過
- 全部使用 type hints；不用 `Any`，除非接外部無型別資料
- 設定從環境變數讀，不寫死；新增的環境變數同步加到 `.env.example`
- Log 一律用 `from radar.common.log import log`（包裝 loggerhelper），不用 `print`、標準 `logging` 或直接 import loggerhelper；服務入口的 `main()` 第一行呼叫 `setup_logging("<服務名>")`，並加上 `@log.catch(level="CRITICAL")`
- 新增相依套件屬於決策分級②，要先開 D-編號

### 資料與架構約定（違反會造成資料錯誤）

- 時間一律 UTC，PTT 的 `Asia/Taipei` 在 parser 轉換
- `post_id` = `<board>.<PTT 文章檔名>`
- 每張 PG 表只有一個寫入者（設計文件 5.4）；標註、推論結果**不可寫回 `posts`**（會造成 CDC 迴圈）
- 爬蟲不碰 PG；不可同時寫 PG 與 Kafka（雙寫）
- Kafka consumer 處理完才 commit；壞資料送 `dlq`，暫時性錯誤重試
- ORM model（`radar.common.db.models`）只描述 PG 表；Kafka 訊息用 pydantic（`radar.common.schemas`），兩者不混用
- 批次寫入用 SQLAlchemy Core，單筆 CRUD 用 ORM（開發規格 2.4）
- Schema 只透過 Alembic migration 變更；已合併的 migration 不可修改，要改就新增一個

### 測試規範

- **每個新增或修改的函式都要有單元測試**，沒有測試的實作不算完成
- 單元測試不連網路、不連真實 Kafka／PG；需要時用 fake 或 mock
- 整合測試放 `tests/integration/`，連 `compose.yaml` 的 kafka／postgres／clickhouse（讀 `IT_*` 環境變數，不用 testcontainers；指令見開發規格 7.26）
- **任何測試都不可對真實 PTT 發請求**，只讀 `tests/fixtures/ptt/` 或使用假 PTT 伺服器（`tests/e2e/fake_ptt.py`）
- 測試名稱描述行為：`test_<情境>_<預期結果>`
- 至少涵蓋：正常路徑、邊界值、錯誤輸入；consumer 另需涵蓋重複訊息（冪等）與 DLQ
- 修 bug 先寫一個會失敗的測試重現它，再修

### Git

- commit 使用 Conventional Commits：`<類型>(<task_id>): 說明`，例 `feat(dashboard-board-trend): ...`
- 不提交 `.env`、爬下來的資料（`data/`）、模型檔（`models/`）

### 文件同步

- **文件必須與程式同步**：行為、資料流、表、topic、訊息格式、API、相依套件有變動時，在同一個 PR 內更新設計文件或開發規格
- 先改文件再改程式；實作中做出新決定時，回寫到文件後才算完成
- 發現文件與實作不一致時，指出來，不要自行決定以哪邊為準
