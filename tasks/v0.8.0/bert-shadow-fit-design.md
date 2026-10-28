# 派工單 bert-shadow-fit-design

- **類型**：docs
- **負責**：architect
- **目標**：依 4 個 BERT 模型的 evaluate 結果，判斷哪個能進 shadow、要怎麼調整，把下一步寫進開發規格 7.27；需要甲方決定的列「待決定」
- **背景**：甲方 2026-10-28 跑完 evaluate，報告在 `models/bert-{macbert-202610280830,ckip-202610280849}{,-int8}/evaluation.md`（主目錄，未進 git，直接讀）。人工測試集 macro-F1：ckip fp32 0.612、ckip int8 0.572、macbert fp32 0.571、macbert int8 0.464（baseline 0.504）。CPU（INFERENCE_THREADS=2、每批 100）：fp32 每批約 70～76 秒，int8 約 23～25 秒；記憶體峰值 RSS 5069～6285 MB。照 7.27「自行決定」：int8 掉分都超過 0.02 → 應用 fp32，但 fp32 不過「每批 < 30 秒」門檻（規定改 max_len 256 重跑）；且 RSS 遠超 D-023 shadow 上限 1.5g。另外每份「LLM 標註者 vs 人工」表都是 0 篇、標題寫「Baseline」，與 baseline 報告不同，疑似 evaluate 的 bug 或資料問題，請一併判斷。Colab 紀錄見 `docs/reports/model-evaluation.md`
- **設計依據**：`docs/development-spec.md` 7.11、7.27（「自行決定」、shadow 表、evaluate 段）；`docs/decisions.md` D-021、D-023
- **相依**：無
- **負責檔案**：
  - `docs/development-spec.md`（7.27）
- **禁區**：不改程式；不寫 `model-evaluation.md`（評估報告另開單）；不推翻已定案決策，超出 D-023 的方案列「待決定」
- **驗收測試**：無
- **驗收條件**：
  - [ ] 說明 RSS 5～6 GB 的來源（模型本身、batch × max_len 的中間張量、evaluate 程序其他部分），是否代表 shadow 實際用量
  - [ ] 給出進 shadow 的具體方案與順序（例：max_len、batch size、int8 取捨、是否要甲方重跑 Colab），每個方案預估耗時與記憶體影響，標明哪些要實測
  - [ ] 判斷「LLM vs 人工」0 篇與「Baseline」標題是否為 bug；是的話列出要開的修正單（負責檔案、驗收條件）
  - [ ] 「待決定」只列決策分級四類（例：放寬 D-023 記憶體上限）；其餘寫進「自行決定」表
- **驗證指令**：`pre-commit run --files docs/development-spec.md`
- **回報檔**：`reports/bert-shadow-fit-design.json`

## 執行資訊（task.py 產生）

- Issue：#192
- 分支：`docs/bert-shadow-fit-design`（從 develop 開出）
- 工作目錄：`.worktrees/bert-shadow-fit-design`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-28

### reports/bert-shadow-fit-design.qa.md

FAIL 59d2f9b

# bert-shadow-fit-design 驗證

## 通過的項目

- `pre-commit run --all-files`（worktree）：trailing whitespace、end of files、check yaml、ruff、ruff format、bandit 全 Passed，rc=0
- `make check`：pre-commit 通過，`1360 passed in 5.24s`
- `git diff --name-only develop...HEAD`：只有 `docs/development-spec.md`（負責檔案），`git status` 乾淨
- 7.27 評估結果表與 `models/bert-*/evaluation.md` 逐項核對一致：
  - macro-F1：ckip 0.612、ckip-int8 0.572、macbert 0.571、macbert-int8 0.464
  - 每批 p50／最大：69.5／72.3、23.2／25.4、70.7／76.4、23.1／23.4 s
  - RSS：5069、5973、6285、6134 MB
  - 差值 0.041、0.040、0.107 皆算對；baseline 0.504 與 spec 359-360 行一致
- 報告 bug 判斷屬實：`evaluate.py` 第 206 行寫死 `## Baseline`；四份報告的「LLM 標註者 vs 人工」全是 0 篇，且依 `card.label_version` 查（evaluate.py 286 行）。修正單引用的 `RuntimeStats`、`measure_runtime`、`_peak_rss_mb`、`load_classifier`、`InferenceSettings`、各測試檔與 `tests/unit/acceptance/bert-classifier/` 都存在
- 計算自洽：attention 100×12×512×512×4 B = 1.26 GB，hidden 0.16 GB，FFN 0.63 GB；平均 183 token 時 padding 約 64%；每批含 ≥512 的機率 1−0.95^100 ≈ 99%；4096 = 8×512 時約 1/12.5；耗時 0.37／0.42／0.29 倍分別換算 26～32 s、約 21 s。這些估計值（token 分布、RSS、耗時倍數）無法由報告獨立核實，spec 已標「需實測」
- 其餘門檻、順序表、修正單表、自行決定表互相一致：0.02、0.01、30 s、4096、順序 1→2→3→(4→5)→6、相依「等 3」、第 9 步回指

## FAIL（1 項）

1. 記憶體門檻前後矛盾，順序 3～5 之間有未定義區間
   - 「進 shadow 的門檻」（spec 約 1381 行）與順序 3 都以 RSS ≤ 1.2 GB 為過關條件，「自行決定」表也寫 RSS 門檻 1.2 GB
   - 順序 5 卻寫「4、5 後仍超過 1.5g 時改問甲方是否放寬 D-023」，回報 `open_questions` 同樣寫 1.5g
   - 重現：讀 `docs/development-spec.md` 7.27，對照 `grep -n "1\.5g\|1\.2 GB" docs/development-spec.md`（1381、1451、1453、1477 行）。若順序 4、5 後 RSS 落在 1.2～1.5 GB，按 1.2 沒過門檻，按 1.5 又不必問甲方，沒有規定要做什麼
   - 修法：順序 5 改成「仍超過 1.2 GB」，或明寫 1.2～1.5 GB 之間的處理
