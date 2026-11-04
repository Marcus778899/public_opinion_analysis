PASS 3acd2e6

# bert-design 驗證（PR #154，docs，第二輪）

## 結論

0 個問題。上一輪 FAIL 1（`bert-integration` 沒有負責檔案）已修。

## 上一輪問題

- `docs/development-spec.md` 7.27「檔案分工」表新增一列：`tests/integration/ml/test_bert_pipeline.py` 屬 `bert-integration`。
- 測試用小 ONNX 模型 helper 放 `tests/helpers/onnx_model.py`，連同 `tests/unit/helpers/test_onnx_model_helper.py` 列在 `bert-skeleton` 的負責檔案，由它完整實作；順序 7 寫明只改自己的測試檔，發現別單錯誤回報 manager。與平行的 3～6 沒有重疊。

## 檢查

1. 只改兩份負責文件。

```
$ git -C .worktrees/bert-design diff develop...HEAD --stat
 docs/development-spec.md                | 181 ++++++++++++++++++++++++++++++--
 docs/realtime-sentiment-radar-design.md |  23 ++--
 2 files changed, 191 insertions(+), 13 deletions(-)
```

2. pre-commit 與單元測試（自己在 worktree 執行）。

```
trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
check yaml...............................................................Passed
ruff (legacy alias)......................................................Passed
ruff format..............................................................Passed
bandit...................................................................Passed
1152 passed in 3.24s
```

3. PR CI 等跑完後全綠。

```
$ gh pr checks 154
Check             pass  41s
Integration Test  pass  6s
Security          pass  28s
```

4. 派工順序（順序 0～11）：順序 1～7 每張單都有 task_id、負責、驗收測試目錄（以 task_id 命名）、相依與平行；負責檔案在「檔案分工」表，8 張單（skeleton、notebook、classifier、model-import、shadow-inference、compare、integration、eval-report）都有列。順序 8、9 標明等甲方交回模型包。`bert-skeleton`、`bert-eval-report` 驗收測試欄為「—」或「無」，理由表內已寫（`make check`＋arm64 建 image；docs 單）。

5. 負責檔案重疊（平行的 2～6）：notebook、classifier（classifier.py／evaluate.py 與其單測）、model-import、shadow-inference（inference/main.py、`test_inference_*.py`）、compare（compare.py、`test_compare.py`）彼此路徑不同，無重疊；`bert-integration` 只有 `test_bert_pipeline.py`，與 `test_inference_*.py`、`test_compare.py` 不同名。

6. 設定值與密鑰：對 diff 新增行搜尋 `token=`、`secret=`、`password=`、`api_key=`、`http(s)://`、`localhost`、4～5 位數、`sk-`、`ghp_`，命中的只有日期（2026-10-21）與表格文字，沒有設定值或密鑰。

7. 內部引用：沿用上一輪確認的各節、D-019、`docs/research/bert-stage8.md`（develop 已有，合併後有效）、migration 0006 不衝突；本輪新增的 `tests/helpers/onnx_model.py`、`tests/unit/helpers/` 在文件內前後一致（7.27「測試」節、檔案分工表）。

## 備註（不列為 FAIL）

- `tests/helpers/` 目前不存在，由 `bert-skeleton` 建立，文件已明寫。
