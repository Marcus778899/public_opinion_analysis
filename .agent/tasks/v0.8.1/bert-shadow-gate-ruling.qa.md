PASS ebbb16b

# QA：bert-shadow-gate-ruling（docs，architect）

## 驗證項目與結果

1. pre-commit：`pre-commit run --files docs/development-spec.md`（在 worktree）。trailing whitespace、end of files、ruff format 皆 Passed，其餘 Skipped。
2. `make check`（在 worktree）：`1384 passed in 5.58s`，結束無錯誤。
3. 只改負責檔案：`git diff develop...HEAD --name-only` 只有 `docs/development-spec.md`；`git status --short` 乾淨。
4. 數字與 `models/bert-ckip-202610280849/evaluation.md` 一致：
   - macro-F1 0.612、每篇 p50 258 ms／p95 305 ms、每批 p50 25.818 s／最大 30.456 s、RSS 載入後 689 MB／峰值 932 MB：與判定表、順序表逐項相符。
   - 順序 2 前 5069 MB：與 7.27 既有表（1425 行）相符。
   - 衍生推算：100 篇 30 s 約每分鐘 200 篇、最大比 p50 多 18%（30.456/25.818），皆正確。
5. 門檻定義在「自行決定」表：1381 行（門檻列）與 1511–1512 行（統計量、補資料量法）都有；寫明 p50 < 30 s、最大 ≤ 60 s、峰值 ≤ 1.2 GB。
6. 三處互相對照：門檻列、順序 3 列（1451 行）、判定小節（1462 起）、「30 s 不放寬」條目（1457 行）的統計量與數值一致；全過 → 順序 6，結論「走 6」與順序表一致；順序 6 的觀察項「不過就」回順序 4，與順序 4／5 的定義不矛盾。
7. 引用對照程式：`make up-shadow`、服務 `inference-shadow`、container `radar_inference_shadow`、profile `shadow`、環境變數 `INFERENCE_SHADOW_MODEL_VERSION`／`INFERENCE_MAX_BATCH_TOKENS`（`.env.example`）、consumer group `inference-shadow-<model_version>`（`roles.py`）、表 `predictions_shadow`、同批共用一個 `predicted_at`（`main.py` 160 行）都存在。

## 非阻擋備註（不列為 FAIL）

- 門檻的統計量是看到結果後才補定義的，文件與回報的 open_questions 都已誠實揭露，並要求甲方核可；第二個條件「最大 ≤ 60 s」是新增的，建議 manager 提請甲方核可時明講。
- 未實際執行 7.27 內的 ClickHouse 查詢與 `memory.peak` 指令（需甲方主機的服務），回報已註明未在甲方主機跑過。
