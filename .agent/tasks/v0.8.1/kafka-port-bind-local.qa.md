PASS a1e7af9

驗證 commit a1e7af9（fix/kafka-port-bind-local）。

1. 驗收條件 1：`infra/docker-compose.yaml` 所有 ports 條目（grep 結果）：kafka_1～3 為 `127.0.0.1:9092:9092`、`127.0.0.1:9094:9094`、`127.0.0.1:9096:9096`；其餘服務也全為 `127.0.0.1:`；檔內 `0.0.0.0` 只出現在 api 的 uvicorn `--host`（容器內監聽，非 port 發布）。
2. 驗收條件 2：`docker compose -f .worktrees/kafka-port-bind-local/infra/docker-compose.yaml --env-file .worktrees/kafka-port-bind-local/.env.example config` 解析成功，kafka_1/2/3 的 ports 為 `host_ip: 127.0.0.1`，published 9092/9094/9096；listener、advertised 設定未變。
3. 驗收條件 3：開發規格 7.20 步驟 3 寫明 Kafka 只綁 127.0.0.1（D-039）與 `localhost:9092,9094,9096`，只寫一處；步驟 6 改為「預期至少 1 則警示（文章或看板）」並保留查看方法。
4. 驗收條件 4：`uv run ruff check .` -> All checks passed!；`uv run pytest tests/unit -q -n 4` -> 1890 passed in 53.41s。
5. 仲裁：舊單測試 `test_guard_kafka_ports_unchanged` 已依仲裁改為 `test_guard_kafka_ports_bound_local`，期望值為 127.0.0.1 版本，與仲裁一致，其他測試未動。
6. 禁區：diff 僅動 infra/docker-compose.yaml、docs/development-spec.md 與兩個測試檔，未動 .env.example、compose.yaml、listener。
7. 非整合單、非 scan 單，無需啟動服務。開發環境 Kafka 尚未重啟，綁定等甲方部署後生效（已在回報的 open_questions）。

問題數量：0
