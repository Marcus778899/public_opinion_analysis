PASS 407d342

# bert-skeleton 驗證（第二輪 review 追加）

## 範圍
- `git diff HEAD~1 HEAD --stat`：只有 `docs/development-spec.md`（8 增 8 刪）；`git diff --stat 573b966 HEAD` 排除該檔後無其他變動，程式、compose、migration 未變。

## 追加 3 條
| 條 | 結果 |
|---|---|
| 1 ckip tokenizer 改 `google-bert/bert-base-chinese` 並釘 revision | 通過。「匯出」tokenizer 項、威脅表「預訓練模型的來源」（含 Google tokenizer repo、card 記 tokenizer 來源與 revision）、自行決定表（理由：ckiplab README 指定；do_lower_case 不在 vocab.txt）三處都已改；舊句「從 vocab.txt 轉換」已刪；ids 一致性檢查維持 |
| 2 需調查改為引用 | 通過。段落改「已調查」，三項各一行，引用調查而不重抄 hash（`grep -E '\b[0-9a-f]{40}\b' docs/development-spec.md` 無結果） |
| 3 D-025 縮成一行 | 通過。「pickle 權重的載入方式：待決定 D-025（選項與建議見 `docs/decisions.md`）；…」，A／B／C 不再重寫 |

## 驗證
- `make check`：pre-commit（trailing whitespace、end of files、yaml、ruff、ruff format、bandit）全 Passed；`1214 passed in 3.61s`。
- `gh pr checks 156`：Check pass 47s、Integration Test pass 2m18s、Security pass 28s。
- `grep -rn "TODO(bert-skeleton)" src tests`：無結果。

## 備註（不構成 FAIL）
- worktree 分支尚未含 develop 的 faae283，所以分支內的 `docs/research/bert-stage8.md` 還沒有「safetensors 與 ckiplab tokenizer」節，D-025 也不在分支的 `docs/decisions.md`；這些引用在 develop（主目錄）已存在，合併後即成立。合併前不需改動。
