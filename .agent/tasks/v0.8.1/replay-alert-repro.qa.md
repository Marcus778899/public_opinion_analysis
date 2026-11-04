PASS acc1ee6

# replay-alert-repro 驗證（第 2 輪，HEAD acc1ee6）

## 結論
上一輪唯一的 FAIL（surge 誤報舊訊息警告）已修：warn_if_replay_topic_dirty 只在 command == replay 時呼叫。照 7.20 重新實跑，surge 沒有 WARNING，replay.alerts 收到 2 則警示。測試與 check 通過。

## 修正內容確認
`git diff 3b3a329 HEAD`：replay.py main() 改成 `if args.command == "replay": warn_if_replay_topic_dirty(kafka)`；7.20 步驟 1 文字改為「`replay`（暖機）開始前若發現舊訊息會印一行警告；`surge` 不檢查（暖機後 topic 本來就有資料）」，與行為一致。新增 test_replay_warmup_no_false_warning.py 與 test_main_surge_does_not_check_topic_for_leftovers。

## 驗收條件
1. 根本原因與證據：回報與 7.20 寫明（殘留的 surge 把 watermark 推到現在，暖機資料被當遲到丟棄，實測 23 個樣本）。本輪未再重現殘留情境（上一輪已查；本輪不改此項）。PASS。
2. 實跑（PASS）：只用 replay.cdc.comments、replay.alerts、新 group heat-replay-1793348379；未讀 .env（KAFKA_BOOTSTRAP_SERVERS、SCHEMA_REGISTRY_URL 以 .env.example 本機值用環境變數傳入）；heat 用 subprocess timeout=210 自行結束。
   - 清空：AdminClient 刪除兩個 replay topic（deleted replay.cdc.comments / deleted replay.alerts），tools/create_topics.py 重建（create replay.cdc.comments (partitions=3)、create replay.alerts (partitions=1)、done）。
   - record -> rc=0，`recorded 5308 messages`
   - heat：`heat consuming replay.cdc.comments as heat-replay-1793348379`
   - replay --speed 1000 -> rc=0，`sent 5308 messages to replay.cdc.comments`
   - surge --post-id Gossiping.M.1000000001.A.BBB -> rc=0，輸出只有 `sent 81 messages to replay.cdc.comments`，沒有任何 WARNING（此為上輪 FAIL 的重點）。
   - read_committed 讀 replay.alerts：ALERT 1 unit_type board / Gossiping；ALERT 2 unit_type post / Gossiping.M.1000000001.A.BBB；`alerts total 2`。heat `timeout-ended: True`。
3. 7.20 內容完整（暖機條件、預期結果、去哪看、停 heat、要清的狀態），警告敘述已與新行為一致。PASS。
4. --help／錯誤提示：本輪只改 main() 的呼叫條件，未動；上一輪已驗 PASS（manager 已裁定 usage 區塊不算問題）。PASS。
5. 測試與檢查（PYTHONPATH=worktree/src）：
   - `uv run pytest tests/unit/acceptance/replay-alert-repro tests/unit/streaming -q` -> `151 passed in 3.01s`
   - `uv run pytest tests/unit -q -n auto` -> `1886 passed in 49.63s`
   - `uv run ruff check .` -> All checks passed!；`ruff format --check .` -> 327 files already formatted
   - `pre-commit run --all-files`（make check 的 lint 部分）-> trailing whitespace／end of files／check yaml／ruff／ruff format／bandit 全 Passed
   - `grep -rn "TODO(replay-alert-repro)" src tests` -> 無結果
   - heat.py 未改（範圍僅 replay.py、測試、docs 7.20）。

## 備註（非判定項目）
- 實跑留下 Quix 內部 topic 與 group heat-replay-1793348379、qa-read-heat-replay-1793348379（replay 專用）；未碰正式 topic。
- 覆蓋率閘門（CI coverage_gate）未跑。
- UAT 留下的 heat PID 74977 在 sandbox 內無法確認，仍請 manager 在 sandbox 外確認。

## 問題
無。
