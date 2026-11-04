APPROVE 9f0b488

# Review spec-docs-sync（PR #246）

依據：`tasks/spec-docs-sync.md`（含兩段追加）、D-034、`reports/spec-docs-sync.qa.md`（第 3 輪 PASS）、`reports/spec-docs-sync.ruling.md`（QA_WRONG 9f0b488）。

## 範圍

- `gh pr diff 246`：只動到 `Makefile`（`seed:` 的 `##` 註解，1 行）和 `docs/development-spec.md`（1.3 make 表、第 6 節進度表 7.28 列、7.21 bot、7.27、7.28 C／派工順序／風險表），都在負責檔案的範圍內；沒有改到程式、測試或 Makefile 指令本身
- 對照 develop：分支的 merge-base 是 792e89b，在 #242、#247 合併之前。直接拿 `git diff develop 9f0b488` 比，會看到 bot、gitleaks 的檔案像是被還原，原因只是分支落後 develop，PR 本身沒有改到這些檔。`git merge-tree --write-tree develop 9f0b488` 可以乾淨合併，所以不會把那些變更倒退回去
- CI：Check、Integration Test、Security 都通過

## 內容與程式一致性（對照 develop）

| 文件位置 | 對照的程式 | 結果 |
|---|---|---|
| 1.3 表（97 行）、`Makefile:56` | `tools/seed_boards.py` 預設 `RADAR_API_URL=http://localhost:8000`；compose 的 `api` 綁在 `127.0.0.1:8000`；README 29 行 | 一致，兩邊的說法相同 |
| 7.21 bot（951 行） | develop `src/radar/bot/main.py`：`POLL_BACKOFF_MAX_S = 30.0`、`_PG_TRANSIENT = (OperationalError, InterfaceError)`；`poll_commands` 遇 `TransientError` 時優先用 `retry_after_s`，沒有才用退避；遇 PG 斷線時退避，且 offset 不前進；其他例外記 WARNING 後跳過，offset 前進；`purge_muted` 遇 PG 斷線記 WARNING，不更新 `last_purge` | 一致。「模組常數」的說法正確（它不是環境變數，不必放進 `.env.example`） |
| 7.27（1317 行） | `import_model(zip_path: Path, models_dir: Path, *, sha256: str \| None = None)`；`tests/unit/ml/test_stage8_interfaces.py` 有檢查參數名稱與 keyword-only | 一致 |
| 7.28 C（1582～1587 行） | `infra/docker-compose.yaml`：服務 `kafka_1～3`、volume `kafka_N_data`、內部 listener `:29092`、healthcheck 只跑 `kafka-broker-api-versions.sh`、`KAFKA_MIN_INSYNC_REPLICAS: 2`、工具路徑 `/opt/kafka/bin/`；`.env.example` 的 `KAFKA_VERSION=4.1.2` | 一致。三條指令都是單行的 `docker compose`，沒有 `cd`、`&&` 或管線；`--under-replicated-partitions` 沒有輸出才換下一台 |
| 進度表 373 行、派工順序 1595 行相依欄、風險表 1663 行 | D-034、PR #224、#225、#229、#230 | 都已改成已定案或已完成；`grep 待甲方` 沒有結果 |

## 非阻擋（不影響結論）

- `docs/development-spec.md:1595` 驗收欄寫的還是「開發環境由甲方改 `.env` 後照上方步驟逐台升級」（未來式），讀起來跟 1582 行的「已升完」不太一致。仲裁已經判定這不在本單範圍內，之後要整理文件時順手改就好

## 問題數量：0
