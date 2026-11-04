PASS 796d3f4

# 驗證證據 e2e-volume-regression

1. 新測試涵蓋全部服務：`merged_sources` 遍歷開發 compose 全部 20 個服務（含 `<<: *app` 錨點展開），與 e2e 以 target 為鍵合併；`offenders` 比對頂層 volumes。develop 上 `uv run pytest tests/unit/e2e_support` -> 26 passed。
2. 能抓違規（我自己對真實 compose 做變異，未改檔，只在記憶體中刪 e2e 覆蓋）：
   - 刪 heat 的 `/app/state` 覆蓋 -> `['heat:/app/state=heat_state']`
   - 刪 bot 的 `/app/log` 覆蓋 -> `['bot:/app/log=app_logs']`
   - 刪 postgres 覆蓋 -> `['postgres:/var/lib/postgresql/data=postgres_data']`
   另有假 compose 測試（未覆蓋、長語法、改掛他處通過）。
3. 文件：`e2e_heat_state` 確實在 infra/docker-compose.e2e.yaml（heat 掛 `/app/state`、頂層 volumes 有宣告）。「推送對象」描述與 `src/radar/bot/repository.py::filter_recipients` 一致：`log.info`、內容 alert_id、unit_type、unit_key、chat_id、原因（chat_settings disabled / post muted）。
4. `uv run pytest tests/unit` -> 1127 passed；ruff check/format、pre-commit（修改檔）全 Passed；無 TODO(e2e-volume-regression)。PR #140 CI：Check pass、Integration Test pass、Security pass。

備註（非 FAIL）：文件寫 log 內容 "chat、unit、原因"，實作另含 alert_id，屬超集，不矛盾。
