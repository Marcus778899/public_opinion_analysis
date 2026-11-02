PASS 16d7c02

# 驗證：bert-model-import（PR #160，HEAD 16d7c02）

結論：實作行為全部符合驗收條件與開發規格 7.27 兩列威脅對策；0 個問題。

## 重新判定（依 manager 補充）

- 16d7c02 是仲裁（TEST_WRONG）後 manager 另派 qa 的 A 工作依仲裁檔修正驗收測試的 commit，並已重新鎖定在 16d7c02；worker 的實作 commit 只有 fbdab12。自行確認：HEAD 即 16d7c02，`git diff 16d7c02 -- tests` 為空（lock 之後驗收測試與 helper 無改動），工作樹乾淨；16d7c02 的內容與仲裁檔建議的程式碼一致。
- CI 全綠由 merge 流程檢查，不屬 qa 判斷項目（查詢時 Check、Integration Test 為 pending，Security pass）。
- 因此下方原先列的「問題 1、2」撤回，不再是 FAIL。

## 問題

1. **驗收測試被 worker 改動**
   - 重現：`git -C .worktrees/bert-model-import log --oneline -- tests/unit/acceptance/bert-model-import` 得 `16d7c02 test(bert-model-import): 依仲裁改寫 card 的 model_version…`（在 feat 分支、由 worker 的實作 commit 序列產生）與 `42f8b4e`（qa 原始）。`git diff fbdab12 HEAD -- tests/unit/acceptance` 顯示 `_members_with_version` 被改。
   - 內容與 `reports/bert-model-import.ruling.md` 建議的程式碼逐字一致，但仲裁指定由 qa（A 工作）修，派工單禁區也寫「不改驗收測試」。測試鎖定被繞過，需 manager 裁示：接受該 commit，或還原成 lock 版本（`git restore --source=<lock> --staged --worktree --no-overlay -- tests/unit/acceptance/bert-model-import`）後由 qa 以 A 工作重做。
   - tests/helpers 沒有被改（`git diff 42f8b4e HEAD -- tests/helpers` 無輸出）。
2. **「PR 的 CI 全綠」未驗證到**：`gh pr checks 160`：Check pending、Integration Test pending、Security pass。待 CI 全綠後才能放行（worker 回報 open_questions 也寫了尚未跑）。

## 已實際驗證（皆自行執行）

- `uv run pytest tests/unit/acceptance/bert-model-import tests/unit/ml/training/test_import_model.py -q` → `32 passed in 0.29s`
- `uv run pytest tests/unit -q` → `1246 passed in 3.71s`
- `pre-commit run --all-files`：trailing whitespace／end of files／check yaml／ruff／ruff format／bandit 全 Passed；`uv run ruff check .` All checks passed；`ruff format --check` 274 files already formatted
- `grep -rn "TODO(bert-model-import)" src tests` → 無結果（exit 1）
- 無 pickle 類格式：白名單只有 `model.onnx`、`tokenizer.json`、`model_card.json`

## 對 7.27 威脅與對策的獨立探測（scratchpad 腳本，用 helper 產 zip，呼叫 `import_model`）

| 情境 | 結果 |
|---|---|
| 正常包 | 匯入成功，只有 `models/<version>/`，沒有 `.import-*` 殘留 |
| zip 內含 `sub/` 目錄項 | ModelPackageError，models 目錄無殘留 |
| 成員 `../model.onnx`（路徑穿越） | ModelPackageError，無殘留 |
| 實際解出超過上限（上限暫改 1000，寫 5000 bytes，以讀出位元組計） | ModelPackageError，無殘留 |
| 不是 zip | ModelPackageError |
| `model_version` = `abc\n`、`../x`、`A`、`-a`、`a/b`、65 字元、`é` | 全部拒絕（fullmatch，非 `$`） |
| 同一包匯入第二次（目標已存在） | ModelExistsError，原資料夾保留 |
| card.files 為空 | ModelPackageError（pydantic 驗證） |
| card 雜湊用大寫 | 接受（程式 `.lower()` 比對，可接受） |
| 雜湊不符 | 由驗收測試涵蓋，通過；先驗後才建 staging，無半套資料夾 |

## 觀察（不列為 FAIL）

- `_read_members` 把最多 2 GB 全讀進記憶體再驗證；規格上限是 2 GB，單機可接受，但低記憶體機器可能先 OOM。
- 目標存在檢查與 `rename` 之間有極小競態（單人本機 CLI，可忽略）。
- `hard-coded` 設定值：`MODELS_DIR` 來自既有 `train.py`；import_model.py 內無寫死 port、網址、token。
