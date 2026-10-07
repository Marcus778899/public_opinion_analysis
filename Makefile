COMPOSE := docker compose -f infra/docker-compose.yaml --env-file .env
COMPOSE_E2E := docker compose -f infra/docker-compose.yaml -f infra/docker-compose.e2e.yaml --env-file .env
UV_ENV := uv run --env-file .env

.PHONY: up up-app down logs migrate topics connector ch-migrate seed api lint test test-int e2e-up e2e e2e-down

up:  ## 啟動基礎設施
	$(COMPOSE) up -d --wait

up-app:  ## 連同 api、scheduler、crawler ×3、ingest 一起啟動（會重新建 image，並自動建表與 topic）
	$(COMPOSE) --profile app up -d --build --wait

down:
	$(COMPOSE) --profile app down --remove-orphans

e2e-down:  ## 停止 e2e 環境並刪除 e2e 專用的資料 volume
	$(COMPOSE_E2E) --profile app down -v --remove-orphans

logs:
	$(COMPOSE) logs -f

migrate:
	$(UV_ENV) alembic upgrade head

topics:
	$(UV_ENV) python scripts/create_topics.py

connector:  ## 註冊或更新 Debezium connector（冪等，需先 make migrate 建立 publication）
	$(UV_ENV) python scripts/register_connector.py

ch-migrate:  ## 套用 ClickHouse 尚未執行的 migration
	$(UV_ENV) python scripts/migrate_clickhouse.py

seed:  ## 透過 API 建立初始看板（需先 make api）
	$(UV_ENV) python scripts/seed_boards.py

api:  ## 本機啟動管理 API（http://localhost:8000/docs）
	$(UV_ENV) uvicorn radar.api.main:app --reload --port 8000

lint:
	uv run ruff check .
	uv run ruff format --check .
	pre-commit run bandit --all-files

test:
	uv run pytest tests/unit

test-int:
	uv run pytest tests/integration

e2e-up:  ## 整套服務 + 假 PTT 伺服器，使用 e2e 專用的資料 volume（不碰開發資料、不連真的 PTT）
	$(COMPOSE_E2E) --profile app up -d --build --wait

e2e:  ## 端到端測試，需先 make e2e-up
	$(UV_ENV) pytest tests/e2e -m e2e
