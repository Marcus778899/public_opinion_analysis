PASS 85a045b

# bert-shadow-fit-design 驗證（第 2 輪）

## 上一輪 FAIL 的修復
- 記憶體門檻矛盾已解決：`grep -n "1\.5g\|1\.2 GB" docs/development-spec.md` 顯示 1381 行（門檻 RSS ≤ 1.2 GB）、1451 行（順序 3 同 1.2 GB）、1453 行（順序 5 改為「仍超過 1.2 GB 就不進 shadow，改問甲方是否放寬 D-023，含 1.2～1.5 GB 之間同樣不進」）、1477 行（自行決定表 1.2 GB）全部一致。1.2～1.5 GB 區間已有明確處理。
- 其餘 1.5g 出現處（1279 shadow 表、1394 D-023、1430、1443）指的是 D-023 的容器硬上限或 OOM kill 條件，與 1.2 GB 進門檻的角色不同，不矛盾。
- 回報 `open_questions` 已同步改成 1.2 GB。

## 檢查
- `pre-commit run --all-files`（worktree）：trailing whitespace、end of files、check yaml、ruff、ruff format、bandit 全 Passed
- `make check`：`1360 passed in 4.75s`
- `git status --short` 乾淨；`git diff --name-only develop...HEAD` 只有 `docs/development-spec.md`（負責檔案）
- 7.27 新節與主目錄 `models/bert-*/evaluation.md` 逐項核對一致：
  - macro-F1：ckip 0.612、ckip-int8 0.572、macbert 0.571、macbert-int8 0.464
  - 每批 p50／最大：69.479／72.259、23.224／25.441、70.688／76.423、23.146／23.367 s
  - RSS：5069、5973、6285、6134 MB
- 內部一致性：門檻 0.02／0.005／30 s／1.2 GB／4096、順序 1→2→3→(4→5)→6、修正單相依（`bert-onnx-length-batching` 等前一張、`bert-derive-max-len` 等 3）、LLM 0 篇與「Baseline」標題的判斷（標題寫死為 bug，0 篇是 v5/v6 label_version 不符）皆互相一致，未發現新的自相矛盾
- 未能獨立核實：token 分布、耗時倍數、中間張量 RSS 等估計值，spec 已標「需實測」，不列為問題

## FAIL
無
