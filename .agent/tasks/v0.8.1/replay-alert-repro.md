# 派工單 replay-alert-repro

- **類型**：fix
- **負責**：backend
- **目標**：照開發規格 7.20 做完回放後，`replay.alerts` 真的會出現警示；回放工具的 `--help` 與錯誤提示照其他 CLI 的標準（UAT v0.8.1 F-1、F-2）
- **背景**：UAT v0.8.1 試了兩種做法：只跑 `surge`，以及先 `record` 加 `replay` 暖機再 `surge`，`replay.alerts` 都是 0 則，heat 也沒有錯誤。7.20 沒寫暖機條件、預期結果、去哪裡看、怎麼停掉回放用的 heat。可疑的設定有 `HEAT_WARMUP_MIN`、`HEAT_STALE_AFTER_MIN`、`HEAT_MAX_DELAY_MIN` 和 watermark，但原因還沒確認。缺 compose 覆寫檔的問題由 #259 處理，不在這張。
- **設計依據**：docs/uat/v0.8.1.md F-1、F-2；開發規格 7.20；PR #258（heat-replay-align）；錯誤處理比照 PR #216、#233
- **相依**：無
- **負責檔案**：
  - `src/radar/streaming/replay.py`
  - `src/radar/streaming/heat.py`（只限回放才會走到的路徑；正式 heat 的預設行為與門檻不變）
  - `tests/unit/streaming/test_replay.py`
  - `tests/unit/streaming/test_heat.py`
  - `docs/development-spec.md`（只限 7.20）
- **禁區**：不改正式 heat 的預設值、偵測邏輯、正式 alerts topic；不改 bot、compose；不寫正式 topic
- **驗收測試**：
  - `tests/unit/acceptance/replay-alert-repro/`
- **驗收條件**：
  - [ ] 回報寫出 F-1 的根本原因與證據，要實際重現過
  - [ ] 照修正後的 7.20 從頭做一次（在開發環境，只用 replay 專用的 topic 與 consumer group），`replay.alerts` 至少收到 1 則文章警示；回報附指令與輸出
  - [ ] 7.20 寫清楚：暖機條件、預期結果、去哪裡看結果、怎麼停掉回放用的 heat、要清掉哪些狀態
  - [ ] 回放工具每個參數都有 `--help` 說明；常見的輸入錯誤只印一行說明、以非 0 結束，不印 traceback
  - [ ] 驗收測試與 `make check` 通過；`grep -rn "TODO(replay-alert-repro)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/replay-alert-repro tests/unit/streaming`；`make check`；回放實跑的輸出
- **回報檔**：`reports/replay-alert-repro.json`

## 執行資訊（task.py 產生）

- Issue：#261
- 分支：`fix/replay-alert-repro`（從 develop 開出）
- 工作目錄：`.worktrees/replay-alert-repro`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-30

### reports/replay-alert-repro.qa.md

FAIL 3b3a329

# replay-alert-repro 驗證

## 結論
照 7.20 從頭實跑，`replay.alerts` 收到警示，文件步驟可用；測試、lint 通過；heat.py 未改。FAIL 的原因是 1 個行為問題（見「問題」）。

## 驗收條件逐條
1. 根本原因與證據：回報寫了（replay.cdc.comments 殘留上一輪 surge，watermark 被推到現在，之後的暖機資料被當遲到丟棄）。本次未另行重現殘留情境；但在乾淨 topic 上照步驟成功，與回報的對照一致。有看到 `replay` 之後 topic 內已有資料時，工具印的警告（見問題 1）。
2. 實跑（PASS）：只用 `replay.cdc.comments`、`replay.alerts`、新 group `heat-replay-1793347724`；未讀 `.env`（KAFKA_BOOTSTRAP_SERVERS、SCHEMA_REGISTRY_URL 用 `.env.example` 的本機值以環境變數傳入）；未動正式 topic 與服務。
   - 步驟 1：AdminClient 刪除 `replay.cdc.comments`、`replay.alerts`，`tools/create_topics.py` 重建（輸出 create replay.cdc.comments (partitions=3) / create replay.alerts (partitions=1) / done）。
   - 步驟 2：`record --since 2026-10-30T02:30:00+00:00 --until 2026-10-30T04:00:00+00:00` -> rc=0，`recorded 5308 messages`。
   - 步驟 3：heat（HEAT_INPUT_TOPIC=replay.cdc.comments HEAT_OUTPUT_TOPIC=replay.alerts HEAT_CONSUMER_GROUP=heat-replay-1793347724 HEAT_STATE_DIR=scratchpad）以 `subprocess.run(timeout=210)` 執行，log：`heat consuming replay.cdc.comments as heat-replay-1793347724`，到時自行結束（timeout-ended: True）。
   - 步驟 4：`replay --speed 1000` -> `sent 5308 messages to replay.cdc.comments`。
   - 步驟 5：`surge --post-id Gossiping.M.1000000001.A.BBB` -> `sent 81 messages`。
   - 步驟 6：read_committed 讀 `replay.alerts`：ALERT 1 `unit_type":"board","unit_key":"Gossiping"`，ALERT 2 `unit_type":"post","unit_key":"Gossiping.M.1000000001.A.BBB"`，`alerts total 2`。符合 7.20 寫的「1 則文章警示、可能 1 則看板警示」。
   - 殘留程序：heat 與驗證指令都自行結束；`ps` 列不出任何 radar.streaming 程序。UAT 留下的 PID 74977 我也沒在 ps 輸出看到（ps 在 sandbox 的可信度有限，仍請 manager 在 sandbox 外確認）。
3. 7.20 內容：暖機條件（同看板 >= 75 分鐘、HEAT_WARMUP_MIN=60）、預期結果、看結果的地方（Kafka UI／read_committed consumer）、停 heat（Ctrl-C／kill，不動正式 heat）、要清的狀態（HEAT_STATE_DIR、group、Quix 內部 topic、兩個 replay topic）都有（PASS）。
4. `--help` 與錯誤（PASS，附註）：record/replay/surge 每個參數都有說明。實測：`surge --post-id bad` rc=2；`replay --file /nonexist` rc=1，輸出 1 行 `error: 讀不了 ...`；`record --since 2026-10-30T02:00:00`（無時區）、`replay --speed 0` 都以 argparse 錯誤結束（無 traceback）。注意 argparse 類錯誤除了錯誤行還會先印 usage 區塊（約 3～5 行），不是嚴格的「只印一行」；我沒有找到比對用的其他 CLI 輸出，未判為失敗，供 manager 判斷。
5. 測試與 check（PASS）：
   - `uv run pytest tests/unit/acceptance/replay-alert-repro tests/unit/streaming -q`（PYTHONPATH=worktree/src）：`148 passed in 3.79s`
   - `uv run pytest tests/unit -q -n auto`：`1883 passed in 62.38s`
   - `uv run ruff check .`：All checks passed；`ruff format --check .`：326 files already formatted
   - `pre-commit run --all-files`：trailing whitespace／end of files／check yaml／ruff／ruff format／bandit 全 Passed（輸出以 tail 截尾，其餘 hook 未顯示）
   - `grep -rn "TODO(replay-alert-repro)" src tests`：無結果
6. heat.py 與正式行為：`git diff develop...HEAD --stat -- src/radar/streaming/heat.py` 無輸出（未改）。replay.py 只在 `main()` 內新增檢查；回放僅用 REPLAY_COMMENTS，未碰正式 topic。

## 問題（FAIL 原因）
1. 警告誤報：`warn_if_replay_topic_dirty` 在 `replay` 與 `surge` 兩個指令都會檢查。照 7.20 步驟 4 暖機後再執行步驟 5 `surge`，topic 本來就有剛暖機的 5308 筆，所以每次正常流程都印 `WARNING replay.cdc.comments still has old messages; ... Delete and recreate the topic first`。實跑輸出：`[16:09:55] WARNING ... still has old messages ...` 接著 `sent 81 messages`，而且該次成功收到警示。文件只說「工具啟動時發現舊訊息會印警告」，使用者在正確流程中會被誤導去清 topic。
   重現：乾淨 topic -> `replay --file x.jsonl --speed 1000` -> `surge --post-id Gossiping.M.1000000001.A.BBB`，surge 一定印該警告。
   應修：只在 `replay`（暖機）前檢查，或 surge 不檢查；補單元測試（surge 在已有暖機訊息的 topic 上不應警告）。

## 備註（非判定項目）
- 回放前我刪除並重建了 `replay.cdc.comments`、`replay.alerts`（replay 專用），會留下 Quix 的 changelog 內部 topic 與 group `heat-replay-1793347724`、`qa-read-heat-replay-1793347724`。
- 步驟 3 要在另一個終端機執行 heat，並等 log 出現 `heat consuming`；我的腳本用固定 sleep 25 秒，文件步驟可行。
- 覆蓋率閘門（CI coverage_gate）未跑。

manager：qa 的註記（argparse 錯誤會先印 usage、再印一行錯誤）不算問題：其他 CLI 也是這樣，驗收測試本來就把 usage 區塊排除在外。這一輪只修 FAIL 的那一項：surge 在暖機之後還印「topic 有舊訊息」的警告，這是誤報。
