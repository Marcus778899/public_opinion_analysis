PASS c75a063

- Makefile 變更只有 up 的 `##` 說明（git diff 75444b2..HEAD）；配方 `$(COMPOSE) up -d --wait` 不變；make -n up 輸出 docker compose -f infra/docker-compose.yaml --env-file .env up -d --wait。
- 說明含 connect unhealthy、--wait 回非 0、開發規格 7.30 B、make up-app；與 spec 第 1695 行已知限制一致。
- pytest tests/unit/test_makefile_up_hint.py -v：2 passed。
- pre-commit run --all-files：全 Passed；uv run pytest tests/unit -q -n auto：2023 passed。
- ruff check/format 對新測試通過；TODO(make-up-connect-hint) 無殘留；git status 乾淨。
- 測試第二條鎖定 up 配方原樣，第一條鎖定說明關鍵字；邊界無其他問題。
