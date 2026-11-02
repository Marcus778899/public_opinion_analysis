PASS bf9a5ce

# dashboard-design 驗證（docs 類，PR #86）

## 範圍檢查
- `git diff --name-only develop...HEAD`：只有 `docs/development-spec.md`、`docs/realtime-sentiment-radar-design.md`，皆在負責檔案內；工作目錄 `git status --short` 乾淨。
- `git diff --stat develop...HEAD`：2 files changed, 100 insertions(+), 1 deletion(-)（與回報一致）。
- 無程式、compose、grafana provisioning、scripts、.claude、contracts 變動（禁區無觸碰）。

## 檢查沒被弄壞
- `pre-commit run --files <兩份文件>`：trailing whitespace、end of files、ruff format 皆 Passed，其餘 Skipped（無對應檔案）。
- 文件內引用對照現況（在 worktree 以 grep／sed 確認）：
  - `posts_latest` 有 `url`、`board`、`created_at`；`comments_latest` 有 `commented_at`、`is_deleted`；`alerts` 有 `value`、`baseline`、`zscore`、`board`、`created_at`；`predictions` 取最新一筆邏輯與 `bot/stats.py` 的 `POST_STATS_QUERY` 相同。
  - `TELEGRAM_SENTIMENT_MIN_SCORE` 預設 0.5（`.env.example:114`、規格 7.23）；migration 目前到 0004，新增 0005 不衝突；`infra/clickhouse/users.d/` 現有 `radar.xml`。
  - 被引用的章節 1.3、4.3、7.20、7.23、10.3、11.1、14.3、15.8 都存在；7.25 沒有撞號。

## 驗收條件
1. 兩案比較與建議：7.25 有比較表（工作量、新相依、維運、`make up` 免手動設定、S7-02 面板、延伸），並有「建議 A」；階段 7 與設計文件 9.1 都有指向 7.25。成立。
2. 查詢來源、面板、派工順序：7.25 列出 2 個 view（0005 migration）、6 個面板（來源與定義）、4 張派工（task_id、負責、負責檔案、驗收測試目錄）及順序/相依。成立。
3. 「需調查」「待決定」「自行決定」分開列：`reports/dashboard-design.json` 的 `open_questions` 四類分列（待決定、需調查、自行決定…），7.25 另有「自行決定」表。成立。

## 備註（不影響判定，manager 處理）
- 7.25 引用 `docs/research/dashboard-grafana.md`，該檔在主目錄是 untracked（`git status` 顯示 `?? docs/research/`），不在 PR 內；合併前需由 researcher／manager 一併提交，否則文件有懸空引用。
- 階段 7 規劃那一列插在進度表的階段 5 列之間（規格約 364 行），順序略怪，可選擇性調整。
- `dashboard-grafana-infra` 與 `dashboard-integration` 的相容性、離線重啟、`$__timeFilter_ms` 邊界等行為尚未實測，已列為後續驗收測試，不屬本單範圍。
