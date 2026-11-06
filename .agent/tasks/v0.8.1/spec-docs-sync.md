# 派工單 spec-docs-sync

- **類型**：chore
- **負責**：backend
- **目標**：補齊 backlog 累積的文件缺口（#234、#231、#65 與 bot 錯誤處理），只改文件與 Makefile 註解，不改行為
- **背景**：#234 是 import-model-hardening 仲裁時的契約建議；#231 是 reports/kafka-version-upgrade.review.md 的 3 項文件建議，開發環境 10-29 已照此升完；#65 是 UAT v0.6.0 F-1，README 已補，Makefile 與開發規格 1.3 還沒補；bot 那項來自 reports/bot-poll-resilience.json 的 open_questions。
- **設計依據**：#234、#231、#65；reports/bot-poll-resilience.json；D-034
- **相依**：bot-poll-resilience（PR #242）合併後才能寫 bot 那項，先做其他三項
- **負責檔案**：
  - `docs/development-spec.md`（只限 1.3 的 make 表、6 的 bot 錯誤處理、7.27、7.28 C）
  - `Makefile`（只限 `seed` target 的註解）
- **禁區**：不改程式、測試、Makefile 指令本身；不改 docs/decisions.md、README.md
- **驗收測試**：無
- **驗收條件**：
  - [ ] 7.27 寫上 `import_model(zip_path, models_dir, *, sha256=None)`；同時寫明：改簽名時要同步修改 `tests/unit/ml/test_stage8_interfaces.py`，並把這個檔列入該單的負責檔案（#234）
  - [ ] 7.28 C 的逐台升級步驟：寫成完整的單行 `docker compose` 指令；寫明換下一台前，`--under-replicated-partitions` 要沒有輸出；「待甲方決定（D-034）」改成已定案（#231）
  - [ ] `make seed` 的前置條件改成：api 已經在跑就好（本機 `make api` 或 docker 啟動的 api 都可以）。Makefile 註解與 1.3 一致（#65）
  - [ ] 開發規格的 bot 章節補上：PG 斷線算暫時性錯誤會重試；單筆 update 出現意外例外時記錄後跳過，offset 前進；Telegram 網路錯誤的退避上限是 `POLL_BACKOFF_MAX_S`。這幾點要與合併後的程式一致
  - [ ] `make check` 通過
- **驗證指令**：`make check`；`git diff develop --stat`
- **回報檔**：`reports/spec-docs-sync.json`

## 執行資訊（task.py 產生）

- Issue：#243
- 分支：`chore/spec-docs-sync`（從 develop 開出）
- 工作目錄：`.worktrees/spec-docs-sync`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

manager：worker 在回報裡提到兩處跟 D-034 矛盾的地方，都納入這張單：一處是第 6 節進度表 7.28 那一列，另一處是 7.28 威脅表裡還寫「Kafka 升 4.1.2 待甲方決定」的地方。兩處都改成：已定案，並依 PR #229 完成。這一列也照 #224、#225、#230 的合併結果更新狀態。bot 那項要等 PR #242 合併，合併後我會通知你。完整的負責檔案清單如下：

- **負責檔案**：
  - `docs/development-spec.md`（只限 1.3 的 make 表、第 6 節的 bot 錯誤處理與進度表 7.28 那一列、7.27、7.28 全節）
  - `Makefile`（只限 `seed` target 的註解）

## 追加 2026-10-29

### reports/spec-docs-sync.qa.md

FAIL 16b8f78

# QA spec-docs-sync（PR #246）

## 問題（1 項）

1. 開發規格 7.28「派工順序」表第 3 列（約 1595 行）`kafka-upgrade-4-1-2` 的相依欄仍寫「待甲方核可」，與 D-034（2026-10-29 定案，decisions.md 189 行）矛盾；開發環境也已升完。驗收條件「文件裡已經沒有跟 D-034 矛盾的待甲方決定」未達成，7.28 全節在追加的負責範圍內。
   重現：`grep -n "待甲方" .worktrees/spec-docs-sync/docs/development-spec.md`，命中 1595 行。
   建議：改成「已定案（D-034），已依 PR #229 完成」，驗收測試欄的「由甲方改 .env 後」也一併改成已完成的敘述。

## 逐條驗證

- 7.27 簽名：文件 `import_model(zip_path, models_dir, *, sha256=None)`，對照 `src/radar/ml/training/import_model.py:90` `def import_model(zip_path: Path, models_dir: Path, *, sha256: str | None = None)`，一致；`tests/unit/ml/test_stage8_interfaces.py` 存在；同步修改與列入負責檔案的說明有寫。PASS
- 7.28 C 指令：三條皆為單行、無 `cd`、`&&`、`|`。服務名 kafka_1~3、具名 volume `kafka_N_data`、內部埠 29092 與 `infra/docker-compose.yaml` 一致，`--under-replicated-partitions` 沒有輸出才換下一台已寫明。PASS（我沒有實際對 Kafka 下指令，只對照 compose 檔與語法）
- 「待甲方決定（D-034）」已改為已定案：7.28 C 與進度表 373 行、風險表 1663 行都已改。但見上面問題 1（遺漏 1595 行）。FAIL
- make seed：Makefile 註解與 1.3 表格都改成「api 已在跑即可」，兩者語意一致；`tools/seed_boards.py` 預設打 `http://localhost:8000`，docker 的 api 也綁 `127.0.0.1:8000`，說法成立。PASS
- bot 段：對照 develop 的 `src/radar/bot/main.py`：`POLL_BACKOFF_MAX_S = 30.0`（48 行）；`TransientError` 優先用 `retry_after_s` 否則退避；`_PG_TRANSIENT = (OperationalError, InterfaceError)` 退避重試且 offset 不前進；其他例外記 WARNING 後跳過、offset 前進；purge_muted 遇 PG 斷線記 WARNING 下一輪再試。文件逐點一致。PASS
- 位置判斷：派工單寫第 6 節，但第 6 節只是階段規格與進度表，bot 的實作細節（Telegram 429/5xx/403 處理）本來就在 7.21，錯誤處理接在同一條 Telegram API 項目下，合理，也符合「同一件事只寫一次」。進度表那列（第 6 節）沒有另寫重複內容。接受。
- 只改文件與 Makefile 註解：`git diff develop...HEAD --name-only` 只有 `Makefile`、`docs/development-spec.md`；Makefile 只動 `seed:` 那行 `##` 註解。PASS
- `make check` 等同內容，在 worktree 實跑：
  - `pre-commit run --all-files`：各 hook 皆 Passed（含 ruff、ruff format、bandit）
  - `uv run pytest tests/unit`（用 -n 4）：`1668 passed in 69.91s`
  - `grep TODO(spec-docs-sync) src tests`：無

## 邊界與寫死設定
- 文件只改段落，沒有新增寫死 port／token；29092 為 compose 內部既有值。
