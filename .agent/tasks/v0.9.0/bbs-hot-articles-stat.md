# 派工單 bbs-hot-articles-stat

- **類型**：chore
- **負責**：backend
- **目標**：只查詢：統計各看板「任一 10 分鐘內新推文 ≥ 10 則」的熱門文章同時篇數 p50／p90／最大值，給 BBS spike 算需要的連線數；不改 repo，PR 作廢
- **背景**：
  - 用開發環境 ClickHouse 的 `comments_latest` 唯讀查詢，取 2026-11-01 之後有資料的期間（避開 7.29 的停機缺口）
  - 「同時」以 10 分鐘滑動視窗計，時間用 UTC；查詢只放 scratchpad，不 commit
  - 開發環境容器用 `docker compose -f infra/docker-compose.yaml --env-file .env …`（不要包 make）；沒在跑就回報，不自行啟動整套服務
- **設計依據**：`docs/development-spec.md` 7.31 C（熱門文章、容量）、D 表、派工順序第 4 列
- **相依**：無
- **負責檔案**：
  - 無（查詢只在 scratchpad）
- **禁區**：不改 repo 任何檔案、不 commit；ClickHouse 只做 SELECT；不碰 PG 與 Kafka；不連 PTT
- **驗收測試**：無
- **驗收條件**：
  - [ ] 回報寫明：統計期間、各看板與全部合計的同時熱門篇數 p50／p90／最大值、熱門文章總數
  - [ ] 回報附實際執行的 SQL 與輸出
  - [ ] 回報寫明定義上的取捨（例：推文時間只到分鐘、資料缺口）
- **驗證指令**：`docker compose -f infra/docker-compose.yaml --env-file .env exec clickhouse clickhouse-client --query "<SQL>"`
- **回報檔**：`.agent/reports/bbs-hot-articles-stat.json`

## 執行資訊（ae task 產生）

- Issue：#320
- 分支：`chore/bbs-hot-articles-stat`（從 develop 開出）
- 工作目錄：`.worktrees/bbs-hot-articles-stat`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
