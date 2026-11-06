# 派工單 shadow-memory-measure

- **類型**：chore
- **負責**：backend
- **目標**：在 shadow 容器的限制下（`inference-shadow` 服務：2 CPU、mem_limit 1.5g、`INFERENCE_THREADS=2`）實測 ckip 512 與 len256 兩版在不同 `INFERENCE_MAX_BATCH_TOKENS` 的記憶體峰值、耗時與 macro-F1，找出能在 1.5g 內穩定運作的組合（本單只量測，不改 repo 檔案）
- **背景**：shadow（ckip fp32、512）在容器內被 cgroup OOM kill（`reports/shadow-restart-investigate.json`）。依 7.27 順序 4，manager 已產生 `models/bert-ckip-202610280849-len256`（`derive_model`，#203）。manager 用下列指令在 shadow 容器內跑 evaluate，仍 exit 137：`docker compose -f infra/docker-compose.yaml --env-file .env --profile app --profile shadow run --rm --no-deps -v <repo>/models:/app/models -v <repo>/data/testset:/app/data/testset:ro inference-shadow python -m radar.ml.training.evaluate --model models/bert-ckip-202610280849-len256`。主機上 evaluate（512、4096）峰值 932 MB，容器內明顯更高，原因未明。調查報告的選項 A（調小 `INFERENCE_MAX_BATCH_TOKENS`）尚未實測
- **設計依據**：`docs/development-spec.md` 7.27「評估結果與進 shadow 的調整」（順序 4～6、觀察表、門檻 RSS ≤ 1.2 GB）；D-023
- **相依**：無
- **負責檔案**：無（只寫回報檔）
- **禁區**：不改程式、compose、`.env`；不刪 volume；不動 primary `inference` 與其他服務；只用 `docker compose -f infra/docker-compose.yaml --env-file .env …`；evaluate 產生的 `models/<v>/evaluation.md` 會被覆寫，量完把最後一次的結果留給 len256 4096 以外的組合時，在回報記下每次數字；不要啟動 `inference-shadow` 常駐服務
- **驗收測試**：無
- **驗收條件**：
  - [ ] 回報一張表：版本（512／len256）× `INFERENCE_MAX_BATCH_TOKENS`（至少 4096、2048、1024）→ 是否 OOM、`memory.peak`、每批 p50／最大、macro-F1（evaluate 在容器內跑完才有）；量法寫清楚（例：容器內讀 cgroup，或放寬 mem_limit 的單次 run 量真實峰值）
  - [ ] 說明主機 932 MB 與容器差異的原因（確認或推測分開）
  - [ ] 依 7.27 門檻（RSS ≤ 1.2 GB、每批 p50 < 30 s、最大 ≤ 60 s、len256 掉分 ≤ 0.02）列出可行組合；沒有可行組合時明說，並列出需要甲方決定的選項（放寬 D-023、只推論新文章）
- **驗證指令**：`docker compose -f infra/docker-compose.yaml --env-file .env --profile app --profile shadow ps -a`
- **回報檔**：`reports/shadow-memory-measure.json`

## 執行資訊（task.py 產生）

- Issue：#204
- 分支：`chore/shadow-memory-measure`（從 develop 開出）
- 工作目錄：`.worktrees/shadow-memory-measure`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`
