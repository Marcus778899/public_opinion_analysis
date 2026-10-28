# 派工單 bert-compare

- **類型**：feat
- **負責**：backend
- **目標**：`python -m radar.ml.training.compare --a <版本> --b <版本> --since <時間>` 從 ClickHouse 比較兩版，輸出 `models/<b>/comparison.md` 與 `data/review/disagreements-<a>-vs-<b>.csv`
- **背景**：階段 8 S8-03。骨架已由 `bert-skeleton`（PR #156）建好；`predictions_shadow` 表由 migration `0006` 建立；表名從 `ml/inference/roles.py` 取
- **設計依據**：`docs/development-spec.md` 7.27「比較」（指標定義）「測試」「自行決定」（推論延遲的起點、角色對照表的位置）
- **相依**：bert-skeleton（已合併）
- **負責檔案**：
  - `src/radar/ml/training/compare.py`
  - `tests/unit/ml/training/test_compare.py`
  - `tests/integration/ml/test_compare.py`
- **禁區**：不改骨架的簽名、migration、`roles.py`、`tests/integration/conftest.py`（屬於進行中的 `bert-shadow-inference`）；查詢全部參數化，不用字串拼接；不改開發規格（實作中做出的新決定列在回報裡，由 manager 安排同步）
- **驗收測試**：`tests/integration/acceptance/bert-compare/`
- **驗收條件**：
  - [ ] 一致率、Cohen's kappa、混淆矩陣（整體、各看板）、對 LLM 標註的 macro-F1 與篇數、不一致文章 CSV、推論延遲 p50／p95／最大、信心分布，皆照 7.27「比較」的定義，對預先寫入的資料算出預期值
  - [ ] `grep -rn "TODO(bert-compare)" src tests` 沒有結果
  - [ ] 整合測試前 `docker compose ls` 確認沒有其他測試堆疊，做完 `down -v`；`make check` 通過
- **驗證指令**：`make check`；`docker compose --env-file .env -f .worktrees/bert-compare/compose.yaml run --rm test`
- **回報檔**：`reports/bert-compare.json`

## 執行資訊（task.py 產生）

- Issue：#164
- 分支：`feat/bert-compare`（從 develop 開出）
- 工作目錄：`.worktrees/bert-compare`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-22

### 負責檔案更新（manager，取代原欄位：同一個 PR 內同步 7.27）

- **負責檔案**：
  - `src/radar/ml/training/compare.py`
  - `tests/unit/ml/training/test_compare.py`
  - `tests/integration/ml/test_compare.py`
  - `docs/development-spec.md`

### 要做的事

- 原「禁區」中「不改開發規格」作廢：把回報 open_questions 的 4 項實作決定（`render_llm_section`、kappa 用整數混淆矩陣算與全同類視為 1.0、延遲線性內插與 CSV 欄位、標註者來源與報告數字格式）精簡寫進 7.27「比較」節或「自行決定」表；只改這些地方（同節其他處由 bert-notebook 在改，不要動）
- 分支已由 manager `pr.py sync` 到最新 develop；重跑 `make check`（整合測試沒改程式可不重跑），更新 `reports/bert-compare.json`
