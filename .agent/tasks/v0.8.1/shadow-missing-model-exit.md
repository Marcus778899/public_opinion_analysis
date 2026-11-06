# 派工單 shadow-missing-model-exit

- **類型**：fix
- **負責**：backend
- **目標**：shadow 推論沒設 `INFERENCE_SHADOW_MODEL_VERSION`（或模型資料夾不存在）時，啟動印一行清楚的設定提示並停止，不進重啟迴圈（#172）
- **背景**：見 #172 與 `docs/uat/v0.8.0.md` F-2：compose 把 `INFERENCE_MODEL_DIR` 組成 `/app/models/${INFERENCE_SHADOW_MODEL_VERSION:-}`，沒設時容器一直重啟，`up --wait` 還顯示 Healthy
- **設計依據**：#172；`docs/development-spec.md` 7.27（shadow 角色與設定）；服務入口規範（CLAUDE.md「程式碼規範」）。怎麼讓容器停住而不是重啟（例：結束碼與 compose `restart` 政策、healthcheck）由 worker 決定；動到 compose 檔就同步更新 7.27 對應描述
- **相依**：無
- **負責檔案**：
  - `src/radar/ml/inference/main.py`
  - `src/radar/common/settings.py`（只限 InferenceSettings 的檢查）
  - `infra/docker-compose.yaml`（只限 `inference-shadow` 服務）
  - `tests/unit/ml/inference/`
  - `docs/development-spec.md`（只限 7.27 shadow 啟動相關描述）
  - `tests/unit/acceptance/shadow-missing-model-exit/`
- **禁區**：不改主推論（primary）的行為；不改其他服務的 compose 設定
- **驗收測試**：
  - `tests/unit/acceptance/shadow-missing-model-exit/`
- **驗收條件**：
  - [ ] shadow 角色在模型版本沒設或模型資料夾不存在時，log 一行說明缺哪個環境變數／哪個路徑，以非 0 結束碼離開，不載入模型、不連 Kafka
  - [ ] 容器不會因此無限重啟，也不會被 `up --wait` 當成 Healthy（說明採用的方式並附實測：未設時 `docker compose ... --profile app --profile shadow up -d --wait inference-shadow` 的輸出；實測用 `INFERENCE_SHADOW_MODEL_VERSION=` 覆寫，不改 `.env`；測完 `stop inference-shadow`）
  - [ ] primary 角色行為不變
  - [ ] 驗收測試、`make check` 通過；`grep -rn "TODO(shadow-missing-model-exit)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/shadow-missing-model-exit tests/unit/ml/inference`；`make check`
- **回報檔**：`reports/shadow-missing-model-exit.json`

## 執行資訊（task.py 產生）

- Issue：#215
- 分支：`fix/shadow-missing-model-exit`（從 develop 開出）
- 工作目錄：`.worktrees/shadow-missing-model-exit`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

### reports/shadow-missing-model-exit.review.md

REQUEST_CHANGES 2a6a5fc

# Review PR #217 shadow-missing-model-exit

## 檢查範圍

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改了負責檔案；compose 只動到 `inference-shadow`；settings.py 沒改（理由見回報） |
| primary 行為 | 沒變：檢查只在 `role is SHADOW` 時跑，ValidationError 在非 shadow 時照舊往上丟 |
| 驗收條件 1 | 符合：缺變數、資料夾不存在、compose 組成 `/app/models/` 三種情況都 rc=78，只有一行 ERROR，不載入模型也不連 Kafka |
| 驗收條件 2 | 設定方向正確；`up --wait` 實測依派工留給 manager 在合併後做 |
| 寫死設定 | 沒有 |
| 測試 | `PYTHONPATH=<worktree>/src uv run pytest tests/unit/acceptance/shadow-missing-model-exit tests/unit/ml/inference -q` → 73 passed（已確認載入的是 worktree 的 `main.py`） |
| 改到的行的覆蓋率 | 不足，見問題 2 |

## `restart: "no"` 的取捨：可以接受，但要寫進文件

- 驗收條件同時要求「結束碼非 0」和「`up --wait` 不可以回報 Healthy」。docker 的重啟政策沒辦法依結束碼區分：`unless-stopped`／`always` 碰到任何結束都會重啟；`on-failure[:N]` 碰到 78 也會重啟，重啟期間 `State.Running` 為 true，`up --wait`（沒有 healthcheck 時）一樣會回報 Healthy，也就是 F-2 原本的問題。缺模型時改用 exit 0 會違反驗收條件 1；在 compose 用 `${VAR:?}` 會讓沒設 shadow 版本的所有 compose 指令都失敗。所以要在 compose 層「缺模型時停住，其他錯誤照樣重啟」，目前沒有簡單的做法，`restart: "no"` 是符合兩個條件最簡單的寫法
- 暫時性錯誤的實際影響：執行中 Kafka 的非致命錯誤由 librdkafka 自己重連，`BatchConsumer._poll_batch` 只記 warning（`common/kafka/consumer.py:131-137`）；ClickHouse 只在啟動時 `load_cache` 讀一次。所以不會自動恢復的只有：啟動那一刻 CH／Kafka 還沒好、遇到致命的 Kafka 錯誤、程式 crash、docker daemon 或主機重開
- shadow 不影響使用者看到的結果（7.27：寫獨立的 topic 和表）；3 天無人值守的驗收已經依 D-031 延到上雲後在 VM 上跑，本機 shadow 先停。因此現階段接受這個取捨。上雲跑 3 天前要重新評估（例如 shadow 加 heartbeat，或改成在程式內對啟動時的 CH／Kafka 重試），列在下方「後續」
- 開發規格 294 行的檢查清單要求新服務設 `restart: unless-stopped`；shadow 是例外，要在 7.27 寫出代價（見問題 3）

## 要修改的地方

1. `src/radar/ml/inference/main.py:205-209` — 只要 `INFERENCE_ROLE=shadow`，任何 `ValidationError` 都會被當成「INFERENCE_MODEL_DIR 未設」，原本的 pydantic 錯誤也被吞掉。compose 一定會給 shadow 設 `INFERENCE_MODEL_DIR`（最少也是 `/app/models/`），所以在容器裡**真正會走到這個分支的，只有其他欄位驗證失敗**的情況，例如 `.env` 的 `INFERENCE_MAX_BATCH_TOKENS`（BOARD 正在等甲方加這個值）或 `INFERENCE_THREADS` 打錯。這時候會印出錯誤的提示，並以 78 停住、不再重啟，排查的人會被誤導。違反 backend-standards §5「錯誤不吞掉」 — 改法：只有在 `e.errors()` 全部都是 `loc == ("model_dir",)` 且 `type == "missing"` 時才呼叫 `exit_missing_model`，其他情況原樣 `raise`。補一個單元測試：shadow＋`INFERENCE_MODEL_DIR` 有值＋`INFERENCE_THREADS=0` → 丟出 `ValidationError`（或 log 裡有 `threads`），且不是 78
2. `tests/unit/ml/inference/test_main.py` — 改到的 `main.py` 行數只有 13/25 被量到（52%）；沒量到的是 195、197、203-214。驗收測試在子行程裡跑，pytest-cov 7.1 預設不量子行程，CI 的 `coverage_gate.py`（門檻 80%）會擋下來（Integration Test job 目前還在 pending） — 改法：在 test_main.py 用 monkeypatch 換掉 `load_classifier`、`ClickHouseClient`、`BatchConsumer` 等，在同一個行程裡直接呼叫 `main()`，用 `pytest.raises(SystemExit)` 驗 code 78，涵蓋三種情況：shadow 缺 model_dir、shadow 資料夾裡沒有 card、primary 照常進到 `load_classifier`。加上第 1 點的新分支，修完用 `--cov` 確認改到的行 ≥ 80%
3. `docs/development-spec.md:1287` — 只寫了 `restart: "no"`，沒寫代價。shadow 要無人值守跑 3 天，負責營運的人需要知道 — 改法：在同一條補一句：「代價：啟動時 CH／Kafka 還沒好、致命錯誤、crash、daemon 重開之後都不會自動恢復；跑 shadow 期間要用 `docker compose ps` 確認，停了就 `make up-shadow`；上雲跑 3 天前重新評估（D-031）」

## 不擋合併的觀察

- `exit_missing_model(problem: str | None)` 的參數可以是 None，型別可以收窄成 `str`（呼叫端已經確認不是 None）
- 改了 `check_shadow_model` 之後，`check_shadow_model(None)` 只會從第 1 點的分支被呼叫；`model_dir is None` 那個判斷還是保留

## 後續（給 manager，不屬於這張單）

- 上雲跑 shadow 3 天前，要決定 shadow 怎麼在無人值守時自動恢復（heartbeat 告警，或啟動時重試），可以併入 #178

## 追加 2026-10-29

### reports/shadow-missing-model-exit.ruling.md

TEST_WRONG d51ba3c

# 仲裁 shadow-missing-model-exit（PR #217）：CI 整合驗收 8 個失敗

## 失敗原因（已確認）

CI run 40810929085 的 log，8 個失敗的測試各有一行（路徑是各測試的 `tmp_path`）：

```
ERROR-(inference|radar.ml.inference.main.exit_missing_model:195)=> shadow 找不到模型 /tmp/pytest-of-runner/.../test_shadow_role_writes_only_s0/model_card.json；請在 .env 設定 INFERENCE_SHADOW_MODEL_VERSION …
```

- `tests/integration/acceptance/bert-shadow-inference/test_shadow_service.py` 的 `env` fixture 設 `INFERENCE_MODEL_DIR=str(tmp_path)`。這是空的資料夾，`load_classifier` 被 monkeypatch 換掉，所以以前從來沒讀過資料夾的內容
- 本單在 `main()` 加了 shadow 啟動檢查（`check_shadow_model`：資料夾裡沒有 `model_card.json` 就以 78 結束），所以 `run_service` 的執行緒在 `load_classifier` 之前就因 `SystemExit` 結束，`done` 沒有被設定，assert 失敗
- primary 的測試（`test_primary_role_still_writes_only_primary_topic`）和 `test_shadow_clickhouse.py` 都通過，與「primary 不檢查」的說法一致
- 沒有另外跑 docker：CI log 已經直接顯示原因，不必在本機重現

## 測試目錄的 git 紀錄

| 目錄 | commit | 判定 |
|---|---|---|
| `tests/unit/acceptance/shadow-missing-model-exit/` | 只有 `9ce8197 test(shadow-missing-model-exit)`（qa） | 沒有被 worker 改過 |
| `tests/integration/acceptance/bert-shadow-inference/` | `0f4b100 test(bert-shadow-inference)`、`61ae81b test(bert-onnx-length-batching)` | 兩個都是 qa 的 test commit，本單沒有碰 |

## 逐條判定

| 測試 | 契約條文 | 判定與理由 |
|---|---|---|
| 本單 `test_shadow_version_blank_in_compose_style_dir_exits_nonzero_and_names_env_var`、`test_shadow_model_dir_not_exist_*`、`test_shadow_with_model_dir_present_still_runs`（資料夾裡有 `model_card.json` 才往下跑） | 開發規格 7.27 第 1287 行：「shadow 啟動時先檢查：`INFERENCE_MODEL_DIR` 未設或沒有 `model_card.json` … 以結束碼 78 離開」；#172／派工單驗收條件 1 | **正確**。compose 在 `INFERENCE_SHADOW_MODEL_VERSION` 沒設時會組成 `/app/models/`，這個資料夾存在，所以只檢查「資料夾存在」抓不到 F-2 的情況，一定要檢查 `model_card.json`。測試不用改 |
| 本單實作 `check_shadow_model`／`main()` | 同上 | **符合契約**。實作不用改 |
| `bert-shadow-inference/test_shadow_service.py` 中用 `env` fixture、以 `InferenceRole.SHADOW` 跑 `run_service` 的 8 個測試 | 7.27 模型包格式（第 81、1261 行：`models/<model_version>/` 一定有 `model_card.json`）；第 870 行「`INFERENCE_MODEL_DIR` 指向 `models/<model_version>/`」；第 1287 行的啟動檢查 | **TEST_WRONG**。fixture 給 shadow 的是一個空資料夾，不是合規格的模型資料夾。照現行契約，shadow 碰到這種資料夾就應該以 78 結束，所以測試的前提和契約互相矛盾。測試要驗的行為（topic、group、快取、冪等、DLQ、threads）跟模型資料夾的內容無關，補上卡片就好，不必改 assert |

## 要怎麼改（給 qa；manager 把這個檔加進本單的負責範圍後重新鎖定）

檔案：`tests/integration/acceptance/bert-shadow-inference/test_shadow_service.py`，只改 `env` fixture：

- 在 `card = make_card(e.model_version)`（約第 102 行）後面加一行，把卡片寫進 `INFERENCE_MODEL_DIR` 指向的資料夾，讓它跟真實的模型包一樣：
  `(tmp_path / "model_card.json").write_text(card.model_dump_json(), encoding="utf-8")`
- `load_classifier` 照舊用 fake（這個檔不讀卡片內容，只需要檔案存在；用 `ModelCard` 序列化，內容也符合格式）
- 不改任何測試函式和 assert。`test_shadow_role_uses_classifier_with_inference_threads` 自己另建的 `card` 只用在 fake 的回傳值，不用處理
- 驗證：`docker compose --env-file .env -f .worktrees/shadow-missing-model-exit/compose.yaml run --rm test`（或只跑 `tests/integration/acceptance/bert-shadow-inference/`），8 個 shadow 測試都通過，跑完 `down -v`

## 契約問題

- 無。第 1287 行是本單在負責範圍（7.27 shadow 啟動描述）內新加的，和模型包格式（第 81、1261 行）一致，review 已經看過。不屬於決策分級的四類

manager：依仲裁 TEST_WRONG，擴大負責範圍，加入舊的整合驗收測試檔（只限 qa 依仲裁補 `env` fixture 的 model_card.json，不改斷言）。更新後的完整清單：

- **負責檔案**：
  - `src/radar/ml/inference/main.py`
  - `src/radar/common/settings.py`
  - `infra/docker-compose.yaml`
  - `tests/unit/ml/inference/`
  - `docs/development-spec.md`
  - `tests/unit/acceptance/shadow-missing-model-exit/`
  - `tests/integration/acceptance/bert-shadow-inference/test_shadow_service.py`

## 追加 2026-10-29

manager：仲裁指出要修的驗收測試在本單驗收測試目錄外，把它併入本單驗收測試清單，讓鎖定涵蓋它（修改內容只限仲裁指定的一行，qa B 會核對）。更新後的完整清單：

- **驗收測試**：
  - `tests/unit/acceptance/shadow-missing-model-exit/`
  - `tests/integration/acceptance/bert-shadow-inference/test_shadow_service.py`
