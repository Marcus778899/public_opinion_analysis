COMPOSE := docker compose -f infra/docker-compose.yaml --env-file .env
UV_ENV := uv run --env-file .env

.PHONY: up up-debug down logs migrate topics lint test test-int

up:  ## 啟動基礎設施
	$(COMPOSE) up -d --wait

up-debug:  ## 連同 Kafka UI（http://localhost:8089）一起啟動
	$(COMPOSE) --profile debug up -d --wait

down:
	$(COMPOSE) --profile debug down

logs:
	$(COMPOSE) logs -f

migrate:
	$(UV_ENV) alembic upgrade head

topics:
	$(UV_ENV) python scripts/create_topics.py

lint:
	uv run ruff check .
	uv run ruff format --check .
	pre-commit run bandit --all-files

test:
	uv run pytest tests/unit

test-int:
	uv run pytest tests/integration
