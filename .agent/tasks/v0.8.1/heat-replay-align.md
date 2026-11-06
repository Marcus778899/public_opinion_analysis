# 派工單 heat-replay-align

- **類型**：fix
- **負責**：backend
- **目標**：熱度回放（7.20 replay／surge）不會推送過期警示給甲方、surge 範例實際觸發得了文章警示、每次回放用全新的 consumer group（#80）
- **背景**：UAT v0.6.0 F-5、F-6、F-8（docs/uat/v0.6.0.md 的「警示重放紀錄」）。F-5：回放用的 heat 把一小時前的看板警示寫進正式 alerts，結果推到甲方的 Telegram。F-6：surge 預設 60 則，低於 `HEAT_POST_MIN_COUNT`=80；而且回放 topic 沒有後續事件，最後一分鐘不會結算。F-8：`heat-replay` 沿用舊 offset，啟動時出現 DESTRUCTIVE STATE RECOVERY。容器內跑回放要用 compose 覆寫檔，這張單不做，寫進 open_questions。
- **設計依據**：#80；開發規格 7.20；`src/radar/common/settings.py` 的 `HeatSettings`
- **相依**：無
- **負責檔案**：
  - `src/radar/streaming/replay.py`
  - `src/radar/streaming/heat.py`（只限輸出 topic 改成可設定）
  - `src/radar/common/settings.py`（只限 `HeatSettings`）
  - `src/radar/common/kafka/names.py`（只限新增回放用的 topic 名稱）
  - `tools/create_topics.py`（只限建立回放用的 topic）
  - `tests/unit/streaming/test_replay.py`
  - `tests/unit/streaming/test_heat.py`
  - `tests/unit/common/test_settings.py`
  - `.env.example`（只限新增選填設定，依 D-009 寫成註解）
  - `docs/development-spec.md`（只限 7.20）
- **禁區**：不改正式 heat 的門檻、偵測邏輯與預設行為（預設輸出仍是正式 alerts topic）；不改 bot；不改 compose
- **驗收測試**：
  - `tests/unit/acceptance/heat-replay-align/`
- **驗收條件**：
  - [ ] heat 的輸出 topic 可以用設定換掉；照 7.20 的回放步驟跑時，警示寫到回放專用 topic，bot 不訂閱這個 topic，所以不會推到 Telegram
  - [ ] surge 的預設則數至少等於 `HEAT_POST_MIN_COUNT`（從設定讀，不寫死）；注入完會在下一分鐘補一筆事件，讓最後一分鐘結算
  - [ ] 7.20 的回放步驟每次都用新的 consumer group（例如加上時間戳），文件寫法和實際行為一致
  - [ ] 開發規格 7.20 同步；驗收測試與 `make check` 通過；`grep -rn "TODO(heat-replay-align)" src tests tools` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/heat-replay-align tests/unit/streaming tests/unit/common`；`make check`
- **回報檔**：`reports/heat-replay-align.json`

## 執行資訊（task.py 產生）

- Issue：#257
- 分支：`fix/heat-replay-align`（從 develop 開出）
- 工作目錄：`.worktrees/heat-replay-align`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

manager：驗收測試已在 d5c3e90 鎖定。介面要照 qa 定的做：
- `HeatSettings.output_topic`，對應環境變數 `HEAT_OUTPUT_TOPIC`，預設 `alerts`
- `names.py` 加一個回放專用的 topic 常數，以 `replay.` 開頭
- 7.20 的寫法用 `HEAT_CONSUMER_GROUP=heat-replay-$(date +%s)`、`HEAT_OUTPUT_TOPIC=replay.alerts`

另外，`names.py` 和 `infra/kafka/topics.yaml` 有既有測試在檢查兩邊一致，所以把 topics.yaml 與那兩個測試檔加進負責檔案。完整清單如下：

- **負責檔案**：
  - `src/radar/streaming/replay.py`
  - `src/radar/streaming/heat.py`（只限輸出 topic 改成可設定）
  - `src/radar/common/settings.py`（只限 `HeatSettings`）
  - `src/radar/common/kafka/names.py`（只限新增回放用的 topic 名稱）
  - `infra/kafka/topics.yaml`（只限新增回放用的 alerts topic）
  - `tools/create_topics.py`（只限建立回放用的 topic）
  - `tests/unit/streaming/test_replay.py`
  - `tests/unit/streaming/test_heat.py`
  - `tests/unit/common/test_settings.py`
  - `tests/unit/common/kafka/test_names.py`
  - `tests/unit/common/kafka/test_topics.py`
  - `.env.example`（只限新增選填設定，依 D-009 寫成註解）
  - `docs/development-spec.md`（只限 7.20）
