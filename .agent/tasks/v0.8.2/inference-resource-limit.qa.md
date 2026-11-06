PASS 862e62b

## 驗證（worktree .worktrees/inference-resource-limit，PYTHONPATH=$(pwd)/src）

- diff（develop...HEAD）只動 `infra/docker-compose.yaml` 的 `inference` 服務（加 `INFERENCE_THREADS: '2'`、`cpus: 2`、`mem_limit: 2g`）與驗收測試；diff 中沒有 `inference-shadow` 相關行，shadow 不變。
- `pytest tests/unit/acceptance/inference-resource-limit -v`：6 passed（cpus、mem_limit、threads、threads 為字串、role 仍 primary、shadow 上限不變）。
- `pytest tests/unit -q -n 4`：1986 passed；`ruff check .`：All checks passed；`ruff format --check .`：333 files already formatted。
- `docker compose -f .worktrees/inference-resource-limit/infra/docker-compose.yaml --env-file .env config --quiet`：exit 0、無輸出（compose 檔合法）。
- 想用 `config inference` 擷取展開後的 cpus／mem_limit：加 pipe 被 hook 擋；不帶 pipe 會印出含密碼的設定，故未執行；`--profile inference config inference` 以 `--no-env-resolution` 試跑回 `depends on undefined service "init"`（profile 選取問題，非本單變更）。cpus／mem_limit／threads 為檔內字面值，沒有 `${}` 插值，由 YAML 解析測試與 `config --quiet` 通過涵蓋；此項為無法直接看展開輸出的限制，不構成驗收缺口。
- 與規格對照：docs/development-spec.md 7.30 C 與派工順序第 6 列（cpus 2、mem_limit 2g、threads '2'）一致。
- `grep TODO(inference-resource-limit)` src tests：無結果。
- 寫死設定：新增值皆為資源上限字面值，非 port／網址／token，符合 D-023／D-042 與規格。
- 邊界：只對 op=c 推論的行為不在本單範圍（派工單說明不改）；實測補積壓由 stability-dev-verify 負責。

問題數量：0
