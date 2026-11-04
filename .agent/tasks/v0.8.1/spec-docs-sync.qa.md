PASS 9f0b488

# QA spec-docs-sync（PR #246，第 3 輪）

仲裁依據：`reports/spec-docs-sync.ruling.md`（QA_WRONG 9f0b488）。上一輪唯一 FAIL（約 1595 行派工順序表驗收欄「由甲方改 .env 後」的寫法）判不成立，本輪不列為 FAIL。

## 逐條驗證（HEAD 9f0b488，實際執行）

- 7.27：`docs/development-spec.md` 1317 行有 `import_model(zip_path, models_dir, *, sha256=None)`，並寫明改簽名要同步修改 `tests/unit/ml/test_stage8_interfaces.py` 且列入該單負責檔案。與 `src/radar/ml/training/import_model.py` 簽名一致。PASS
- 7.28 C：三條皆單行 `docker compose -f infra/docker-compose.yaml --env-file .env ...`，無 cd、&&、|；`--under-replicated-partitions` 沒有輸出才換下一台已寫明；「待甲方決定（D-034）」改為已定案。`grep -n "待甲方" docs/development-spec.md` 無輸出。PASS
- 追加：進度表 7.28 列（373 行）與威脅表（1663 行）已改為已定案、依 PR #229 完成，並依 #224、#225、#230 更新。PASS
- make seed：Makefile 56 行註解與 1.3 表格一致（api 已在跑即可）。PASS
- bot（951 行）：對照 `src/radar/bot/main.py`：`POLL_BACKOFF_MAX_S = 30.0`（48）、`_PG_TRANSIENT = (OperationalError, InterfaceError)`（50）退避重試，其他例外記 WARNING 跳過、offset 前進。文件一致。PASS
- 範圍：`git diff develop...HEAD --stat` 只有 `Makefile`（1 行註解）與 `docs/development-spec.md`。PASS
- `make check` 等同內容：
  - `pre-commit run --all-files`：全部 Passed（ruff、ruff format、bandit 等）
  - `uv run pytest tests/unit -n 4`：`1668 passed in 62.75s`
  - `grep -rn "TODO(spec-docs-sync)" src tests`：無輸出

## 邊界與寫死設定
文件沒有新增寫死 port／token；29092 為 compose 內部既有值。

## 非阻擋觀察（不影響判定，依仲裁）
- 派工順序表第 3 列驗收測試欄仍是「由甲方改 .env 後照上方步驟逐台升級」，與 7.28 C「開發環境已於 2026-10-29 升完」讀起來不一致；之後可另外處理。

## 問題數量：0
