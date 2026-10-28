# 派工單 bert-design

- **類型**：docs
- **負責**：architect
- **目標**：階段 8 BERT 與 shadow 比較的設計（S8-01～S8-03），含派工順序
- **背景**：D-019：agent 準備 fine-tune notebook、模型匯出與評估流程，甲方在 Colab／Kaggle 跑訓練並交回模型檔，設計要寫清楚交付物（notebook 位置、輸入資料怎麼匯出、模型檔格式與放置路徑，模型檔不進 git）。新套件（transformers、onnxruntime 等）、模型選擇、推論資源屬決策分級②，列成待決定；不確定的外部資訊（模型授權、CPU 推論延遲、ONNX 匯出可行性）列「需調查」交給 researcher。sandbox 只開放既有網域，Hugging Face 等下載在 agent 端可能被擋，設計要考慮
- **設計依據**：`docs/development-spec.md` 階段 8 與第 7 章 inference 相關節；`docs/realtime-sentiment-radar-design.md`（推論、`model_version`、15.8 信心門檻）；`docs/reports/model-evaluation.md`（階段 3 baseline）；`src/radar/ml/`
- **相依**：無
- **負責檔案**：
  - `docs/development-spec.md`
  - `docs/realtime-sentiment-radar-design.md`
- **禁區**：不改程式、compose、相依套件（骨架等甲方決定待決定後再派）；不改 `docs/reports/model-evaluation.md`（評估結果之後由實作單寫）；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] 做法：fine-tune 流程與交付物、shadow 並行（consumer group、`model_version`、資源）、ClickHouse 比較查詢（macro-F1、不一致文章、延遲），寫進設計文件或開發規格階段 8
  - [ ] 威脅與對策（模型檔來源與完整性、新服務的對外介面）
  - [ ] 實作派工順序：task_id、負責、負責檔案、驗收測試目錄（每張單自己的子目錄，以 task_id 命名）、可平行與否；標出哪一步要等甲方交回模型檔
  - [ ] 「需調查」「待決定」「自行決定」分開列在回報；待決定只列決策分級四類
- **驗證指令**：`git diff --stat develop`
- **回報檔**：`reports/bert-design.json`

## 執行資訊（task.py 產生）

- Issue：#152
- 分支：`docs/bert-design`（從 develop 開出）
- 工作目錄：`.worktrees/bert-design`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-21

### reports/bert-design.qa.md

FAIL a093a56

# bert-design 驗證（PR #154，docs）

## 結論

1 個問題（派工順序缺 `bert-integration` 的負責檔案）；其餘檢查通過。

## FAIL 1：`bert-integration` 沒有負責檔案

- 位置：`docs/development-spec.md` 7.27「檔案分工」表與「派工順序」表（順序 7）
- 檔案分工表列了 `bert-skeleton`、`bert-notebook`、`bert-classifier`、`bert-model-import`、`bert-shadow-inference`、`bert-compare`、`bert-eval-report`，沒有 `bert-integration`。順序 7 只有驗收測試目錄 `tests/integration/acceptance/bert-integration/`，沒有「負責檔案」。
- 這張單是整合單，測試內要產生小 ONNX 模型（fp32 與 int8）並跑通整條流程。產生模型的 helper、共用 fixture 放哪裡、由誰改，文件沒有寫；manager 派單時填不出「負責檔案」，或會與骨架單「驗收測試上層的共用 fixture」重疊。
- 重現：`sed -n 1234,1392p docs/development-spec.md`，在「檔案分工」表搜尋 `bert-integration`，只在「派工順序」出現。
- 建議：補一列 `bert-integration` 的負責檔案（至少測試用小模型 helper 的位置），或寫明它沒有負責檔案、只含驗收測試目錄。

## 備註（不列為 FAIL）

- `bert-skeleton`、`bert-eval-report` 的驗收測試欄寫「—」。前者以 `make check` 與 arm64 建 image 驗收，後者是 docs 單，理由已寫在表內。
- 派工單的 `docs/research/bert-stage8.md` 在 develop 已有（33c2421），分支從 9e9c118 開出，所以 worktree 看不到；合併後引用有效。

## 通過項目與原始輸出

1. 只改負責的兩份文件。

```
$ git -C .worktrees/bert-design diff develop...HEAD --stat
 docs/development-spec.md                | 179 ++++++++++++++++++++++++++++++--
 docs/realtime-sentiment-radar-design.md |  23 ++--
 2 files changed, 189 insertions(+), 13 deletions(-)
$ gh pr view 154 --json files
docs/development-spec.md
docs/realtime-sentiment-radar-design.md
```

2. 我自己在 worktree 跑 `make check` 的兩個步驟（`make` 本身包 pre-commit 與 pytest）。

```
$ pre-commit run --all-files
trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
check yaml...............................................................Passed
ruff (legacy alias)......................................................Passed
ruff format..............................................................Passed
bandit...................................................................Passed
$ uv run pytest tests/unit -q
1152 passed in 3.73s
```

3. PR CI 全綠（我查詢時）。

```
$ gh pr checks 154
Check             pass  32s
Integration Test  pass  7s
Security          pass  28s
```

4. 設定值與密鑰：對 diff 新增行搜尋 `token=`、`secret=`、`password=`、`api_key=`、`http(s)://`、`localhost`、4～5 位數 port、`sk-`、`ghp_`，沒有命中。文件只寫變數名稱（`INFERENCE_THREADS`、`INFERENCE_BATCH_SIZE`、`INFERENCE_ROLE`、`INFERENCE_SHADOW_MODEL_VERSION`、`INFERENCE_MODEL_VERSION`、`TELEGRAM_SENTIMENT_MIN_SCORE`）。其中 `INFERENCE_BATCH_SIZE` 在 `.env.example` 已有，其餘為新增，由 bert-skeleton 加入。

5. 內部引用都對得上：
   - 開發規格：3.4（labels）、7.11、7.18、7.19、S3-06、階段 8 → 7.27
   - 設計文件：8.4、15.8
   - D-019 在 `docs/decisions.md:144`
   - `docs/research/bert-stage8.md` 在 develop
   - `POST_STATS_QUERY`、`SENTIMENT_QUERY` 在 `src/radar/bot/stats.py`
   - `PROMPT_VERSION`、`LABEL_PRIMARY` 在 `src`
   - `.gitignore` 含 `/models/`、`*.onnx`
   - `posts_latest`、`posts_history` 在 migration 0001
   - 現有 migration 到 0005，新增 0006 沒有衝突

6. 派工順序表（順序 0～11）：
   - 順序 1～7 都有 task_id、負責、相依與平行。
   - 驗收測試目錄都以 task_id 命名，並符合既有 `tests/unit/acceptance/<task_id>/`、`tests/integration/acceptance/<task_id>/` 慣例。
   - 順序 8、9 標明等甲方交回模型包。
   - 負責檔案在「檔案分工」表，只缺 `bert-integration`（見 FAIL 1）。
