PASS 116ced8

# bbs-spike-design 驗證（PR #318，docs 單）

## 驗收條件對照

1. 開發規格新增 spike 一節：PASS。`docs/development-spec.md` 新增 7.31，含 A 要回答的問題（Q1～Q6）、B 實驗步驟與頻率上限（P0／P1／P2／尾段／重跑，登入 3 次、間隔 10 分鐘、讀取 ≥20 秒、send ≥1 秒、立即停止條件）、C 量測方法（U/L/E 三值、p50(E) 判定、網頁版配對基準、樣本下限、導入門檻 3 條）、F 報告位置（`docs/reports/bbs-spike.md`）與格式（8 段、≤150 行）。另有 D 分工、E 資料對應、威脅表、自行決定表。
2. 派工順序、需調查、待決定：PASS。「檔案分工與派工順序」表有 6 列（task_id、負責、通道、相依、負責檔案、驗收測試）；「調查結果與處置」表列外部事實與可信度；「待決定」3 項（②、④、①④）附建議，3 號有狀態表。
3. `.env.example` 有帳密變數名稱不含值：PASS。新增 `# PTT_BBS_USERNAME=`、`# PTT_BBS_PASSWORD=`，寫成註解（D-009），值為空。

## 實際執行

- `git -C .worktrees/bbs-spike-design diff --stat develop...HEAD`：`.env.example | 6 ++`、`docs/development-spec.md | 208 +++-`，2 files changed。只動負責檔案，未碰 `src/`、`tools/`、`infra/`、`docs/domain/`。
- `pre-commit run --all-files`（make check 的第一段）：trailing whitespace、end of files、check yaml、ruff、ruff format、bandit 全部 Passed。
- `uv run pytest tests/unit -q -n auto`：`2023 passed in 50.32s`。

## 對照程式與文件的事實查核

- 規格引用的 7.4、7.5、7.10、7.15、7.22、7.28、7.29 與 3.2 皆存在。7.22 的 p90 19.0 分鐘、階段 1 的 0.53 次／秒與規格引用數字相符。
- `counts_event` 在 `src/radar/streaming/heat.py:186` 確實只計 `op=c`，與「已知衝突」所述一致。7.15 確實以 `crawled_at` 判斷快照新舊且只同步不舊的快照，與推論一致。
- `parse_comment_time` 位於 `radar/collector/parsers/ptt_time.py`，與 E 表一致。`tools/*` 在 `.coverage-exempt`，與派工順序註記一致。
- `.gitignore` 有 `/data/`，與「原始資料在 `data/spike/bbs/` 不進 repo」一致。
- 登入次數帳：P0 1 次＋P1／P2 1 次＋重跑 1 次＝3 次，與上限一致。理論值 C≈67 秒、p50≈34 秒的算式自洽。
- 寫死設定值：新增段落與 `.env.example` 沒有帳密、token、網址形式的密鑰；只有公開端點主機名稱與變數名稱。
- scan 通道：本單沒有使用，不適用。
- 整合單項目：本單為 docs，不適用。

## 問題

0 個 FAIL 項目。以下為不影響判定的備註，供 manager 判斷：

1. 本分支基底是 3c1752e，不含 develop 上較新的 `docs/research/bbs-spike.md`（4b36951）。規格引用該檔，worktree 內暫時找不到，合併進 develop 後才有，不算缺陷。
2. 回報 `open_questions` 提到 researcher 對 www.ptt.cc 發過 2 次 WebFetch（403），違反不連線指示。由 manager 判斷是否追究，不是本單的驗收項。
3. 規格內「PyPtt 原始碼事實」來自 GitHub commit cfb2bd9，未對照 2.3.16 發布檔。規格已要求 `bbs-spike-tool` 開工先核對，這裡只是提醒。
4. 規格的待決定 1～3 要 manager 開 D-編號並由甲方決定後，才能派 `bbs-spike-tool`。
