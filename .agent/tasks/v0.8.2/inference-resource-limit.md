# 派工單 inference-resource-limit

- **類型**：fix
- **負責**：backend
- **目標**：compose `inference` 加資源上限 `cpus: 2`、`mem_limit: 2g`、`INFERENCE_THREADS: '2'`（#289）
- **背景**：
  - v0.8.1 換 ckip 模型後補積壓時 cgroup 峰值約 1.46 GB（含 page cache），比照 D-023 shadow 但 1.5g 不夠，改 2g
  - 只對 `op=c` 推論是預期行為（S4-02、7.18），不改
  - shadow 的設定不動；開發環境的實測驗證由 `stability-dev-verify` 做，本單只改 compose
- **設計依據**：`docs/development-spec.md` 7.30 C 與派工順序第 6 列、推論部署段落；D-023、D-042
- **相依**：connect-resilience（已合併）
- **負責檔案**：
  - `infra/docker-compose.yaml`（只限 `inference` 服務）
- **禁區**：不改文件（與 7.30 不符時回報 manager）；不改 `inference-shadow` 與其他服務
- **驗收測試**：
  - `tests/unit/acceptance/inference-resource-limit/`
- **驗收條件**：
  - [ ] compose `inference` 的 `cpus` 為 2、`mem_limit` 為 2g、`INFERENCE_THREADS` 為 `'2'`
  - [ ] shadow 的設定不變
  - [ ] `make check` 通過、CI 綠燈
- **驗證指令**：`make check`；`uv run pytest tests/unit/acceptance/inference-resource-limit -v`；`docker compose -f infra/docker-compose.yaml --env-file .env config --quiet`
- **回報檔**：`.agent/reports/inference-resource-limit.json`

## 執行資訊（ae task 產生）

- Issue：#303
- 分支：`fix/inference-resource-limit`（從 develop 開出）
- 工作目錄：`.worktrees/inference-resource-limit`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
