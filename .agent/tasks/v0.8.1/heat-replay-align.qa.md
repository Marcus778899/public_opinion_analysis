PASS 8a8406a

# QA heat-replay-align（HEAD 8a8406a）

## 驗收條件
1. heat 輸出 topic 可設定：`HeatSettings.output_topic`（`HEAT_OUTPUT_TOPIC`，預設 `alerts`）；`heat.py` 的 `build_app` 改用 `settings.output_topic`，唯一改動；names.py 加 `REPLAY_ALERTS="replay.alerts"`，topics.yaml 加 `replay.alerts`（create_topics 讀 topics.yaml，會建）。PASS
2. bot 不訂閱 replay.alerts：`src/radar/bot/main.py:304 topics=[names.ALERTS]`，bot 無其他 topic 參照。PASS
3. surge 預設則數：`--count` 預設 None，執行時取 `HeatSettings().post_min_count`（不寫死）；注入後 `surge_tail_event` 補一筆 floor=start_floor+count、時間 now+1 分鐘。PASS
4. 7.20 步驟：`HEAT_INPUT_TOPIC=replay.cdc.comments`、`HEAT_OUTPUT_TOPIC=replay.alerts`、`HEAT_CONSUMER_GROUP=heat-replay-$(date +%s)`，與 .env.example 註解、程式變數名一致，文件寫法可直接照做。PASS
5. TODO grep：`grep -rn "TODO(heat-replay-align)" src tests tools` 無結果。PASS

## 正式 heat 預設行為不變
git diff develop...HEAD 對 heat.py 只有 import 移除與 topic 來源一行；偵測邏輯、門檻（HeatConfig）未動；預設 output_topic="alerts" 與原 names.ALERTS 相同。PASS

## 尾事件時間戳
tail 的 `__source_ts_ms` 與 commented_at 都是 now+1 分鐘。讀 heat.py：event_minute 用 source_ts_ms；is_fresh 的 delay 為 0 不被丟棄；advance 讀到下一分鐘會結算 range(watermark, minute)，即結算最後一分鐘。未來時間只寫在 `replay.cdc.comments`，正式 heat 讀 `cdc.public.comments`，不會誤判。PASS

## 實際執行
- `PYTHONPATH=<worktree>/src uv run --no-sync pytest tests/unit/acceptance/heat-replay-align tests/unit/streaming tests/unit/common -q` -> 358 passed in 4.05s
- `ruff check .` -> All checks passed!；`ruff format --check .` -> 325 files already formatted
- `uv run --no-sync pytest tests/unit -q -n 4` -> 1830 passed in 145.81s
- pre-commit 未另跑（ruff 檢查與全部單元測試已通過）。

## 未做／備註（非 FAIL）
- 未用整合測試 compose 實跑 surge + heat：尾事件結算是依 heat.py 程式與單元測試判定，沒有端到端實跑；worker 的 open_questions 也已列出。建議甲方回放驗收時實測。沒有啟動任何容器，不需 down -v。
- 小瑕疵：heat.py 的 `build_app` docstring 仍寫「輸出到 alerts」，與可設定不一致，不影響行為。
- 容器內回放需 compose 覆寫檔，既有環境需先 `make topics` 建 replay.alerts，已在 open_questions。
