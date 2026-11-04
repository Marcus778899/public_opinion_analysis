PASS 854e0ea

# QA pipeline-gap-design（docs 單，PR #221）

## 檢查項目與結果

1. 只改兩份文件：`git diff --name-only develop...HEAD` 只有 `docs/development-spec.md`、`docs/realtime-sentiment-radar-design.md`；worktree `git status --short` 為空。commit：308888e、854e0ea。
2. `pre-commit run --all-files`（在 worktree）：trim trailing whitespace、fix end of files、check yaml、ruff (legacy alias)、ruff format、bandit 全部 Passed。
3. `make check`（在 worktree）：`1522 passed in 61.51s`，lint 無錯。
4. 內部引用：
   - 開發規格 7.28（補抓 A、停擺偵測 B、Kafka C、派工順序、自行決定、需調查）與 7.29（停機缺口 9 段，D-032）存在，標題層級連續接在 7.27 後、第 8 章前。
   - 引用 7.28/7.29 的位置（3.1、Key 表、進度表、風險清單、7.29 內回指 7.28 A/C）全部指到存在的小節；設計文件引用的 4.2、4.4、4.6、6.4、5.4 皆存在。
   - 「待甲方決定（D-034）」：`docs/decisions.md` 有 `### D-034 Kafka 要不要從 4.1.0 升到 4.1.2`（主目錄未提交的修改，位於「待決定」區）；文件中不再有「D-待定」字樣。
   - 派工順序表：1 crawl-backfill-depth（schemas、enums、tasks、crawler、scheduler、tests/unit/collector、tests/e2e）與 2 pipeline-stall-alert（cdc/watchdog、settings、clickhouse、.env.example、tests/unit/cdc）的 src 與測試目錄不重疊；共用的 `tests/unit/common/` 已註明依檔名分開（1：test_schemas/test_tasks；2：test_clickhouse/test_settings）。3 與 2 都改 `.env.example`，已標明排在 2 之後。三張表（需調查、待決定=D-034、自行決定）齊全。
   - `CDC_WATCHDOG_REQUEST_TIMEOUT_S` 已存在於 `.env.example`（現有設定），與文件「沿用」說法一致；新增的 `CDC_WATCHDOG_STALE_ALERT_S` 列在順序 2 的 `.env.example` 修改中。
5. 驗收條件逐條：補抓（資訊來源、誰查 PG、訊息格式、硬上限 80 頁、請求量估算表）有；停擺偵測（訊號、門檻 30 分、cdc-watchdog、healthchecks email、Kafka 升級待決）有；停機缺口日期 7.29 有；派工順序與三張表有。

## 備註（非 FAIL，未列入問題數）

- `docs/development-spec.md` 第 4 行「最後更新：2026-10-28」未隨本次修改更新（manager 合併時可順手改）。
- 內容正確性（如 ClickHouse 實測間隔、KAFKA-19888 版本）依回報的查證，本次未重查外部資料。
