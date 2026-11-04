# CLAUDE.md（團隊共用規範）

所有 agent 啟動時都會讀這份。只放永遠成立的規則，越短越好；情境知識放 skills。

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
- 營運腳本（建 topic、ClickHouse migration、註冊 connector、seed）放 `tools/`；`scripts/` 不放專案程式（D-006；v1 流程腳本已移除）
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

<!-- agent-engineering:begin（由 ae 管理：導入時加入、升級時更新；不要手改，專案規範寫在這個區塊外） -->
## Agent 團隊（agent-engineering）

所有 agent 啟動時都會讀這段。只放永遠成立的規則；情境知識放 skills。

@.agent/BOARD.md

- 布告欄（`.agent/BOARD.md`）上的「已定案決策」不可推翻；與之矛盾時停下來回報 manager
- 只有 manager 可以改布告欄（透過 `ae board`）、README.md、docs/decisions.md
- 每件工作都有派工單 `.agent/tasks/<task_id>.md`（task_id 是有意義的名稱，例 `todo-create-api`）；只在派工單的工作目錄 `.worktrees/<task_id>` 修改「負責檔案」；主目錄只寫自己角色規定的檔（回報與證據 `.agent/reports/`，uat、researcher、security 各自的 `docs/` 子目錄），其他一律不碰；過去階段的派工單封存在 `.agent/tasks/<tag>/`
- 分支：`main` ← `develop` ← `feat/`、`fix/`、`chore/`…；主目錄永遠停在 develop；不可直接 git push、merge、rebase、切換分支，一律透過 `ae`。本專案實際的分支名稱與文件目錄以 `ae config` 為準（這裡與角色檔寫的 develop、main、docs/ 是預設值）
- 業務規則與術語：`docs/domain/`（`README.md` 是索引，用到哪條讀哪個檔）；跟程式、派工單矛盾時以它為準並回報；只有 architect 在設計單裡修改
- 既有專案的舊文件：`docs/inventory/`（`README.md` 是總覽，各子目錄的逐檔清單附摘要與讀法）；原檔不搬不改，要引用就照清單找
- 需要甲方決定的事寫成 D-編號，集中在 `docs/decisions.md`；其他文件只引用編號
- 決策分級：只有這四類開 D-編號問甲方——①範圍（做不做、做多少）②成本與外部依賴（付費服務、新技術棧或套件）③品牌與對外語氣（品牌色、名稱、文案語氣、視覺方向）④不可逆或有風險（刪資料、權限、資料遷移、安全與法規；降低防護也算，例：資安掃描排除整個路徑、關掉規則）。資安掃描的誤判不算④：architect 可以只針對那一類誤判加窄規則，在忽略設定裡附理由，並證明同樣格式的真密鑰仍會被抓到，發版前由 security 逐條追認。其他可逆、在範圍內的細節（互動方式、版面、元件、欄位排序、命名…）由負責角色自己決定，寫進設計或 UI 規格的「自行決定」表，甲方核可設計時一起看
- 設定值（port、domain、token…）只放 `.env`；文件與程式只寫變數名稱；不可讀 `.env`
- 文件精簡：同一件事只寫一次，其他地方引用
- 「完成」必須附實際執行的驗證指令與輸出；沒跑過不算完成
- 回報格式依工具的 `contracts/report.schema.json`（`.claude/skills/agent-engineering/contracts/`；做派工單的角色都要寫）
- 甲方常態授權（甲方只做決策，其他由 manager 推進）：manager 可自行執行 `ae task`、`ae board`、`ae docs`、`ae check-env setup`、`ae release open`，以及 `ae pr` 的 `lock`、`open`、`record`、`ruling`、`sync`、`next`、`merge`（merge 由程式檢查 qa、review、CI 都通過才合併到 develop），以及 `gh issue create --label backlog`（minor 問題、medium／low 資安發現排進 backlog）；甲方關卡只有 `ae board scope`（確認本輪範圍與驗收條件）、`ae pr approve`、`ae pr unblock`、`ae release finish`，會跳確認視窗
- Bash 在 sandbox 裡；docker 只能直接下 `docker compose …`（唯一在 sandbox 外的例外），不要包在 make、script 裡或跟 `cd`、`&&` 寫在同一個指令
<!-- agent-engineering:end -->
