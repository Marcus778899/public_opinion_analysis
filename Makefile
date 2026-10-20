COMPOSE := docker compose -f infra/docker-compose.yaml --env-file .env
COMPOSE_E2E := docker compose -f infra/docker-compose.yaml -f infra/docker-compose.e2e.yaml --env-file .env
UV_ENV := uv run --env-file .env
PRE_COMMIT_VERSION := 4.6.0
# NOTE: 開發與 e2e 共用 compose 專案與容器名稱，不能同時運作；以假 PTT 容器判斷目前是哪一個（#41）
E2E_RUNNING := docker ps -aq --filter name=^radar_fake_ptt$$

.PHONY: setup ci-setup check coverage stop-e2e stop-dev up up-app up-labeling up-inference up-alerting testset human-label down logs migrate topics connector ch-migrate seed api lint test test-int e2e-up e2e e2e-down

up: stop-e2e  ## 啟動基礎設施
	$(COMPOSE) up -d --wait

up-app: stop-e2e  ## 連同 api、scheduler、crawler ×3、ingest 一起啟動（會重新建 image，並自動建表與 topic）
	$(COMPOSE) --profile app up -d --build --wait

up-labeling: stop-e2e  ## 啟動串流抽樣標註（S3-08，會持續呼叫 LLM API）
	$(COMPOSE) --profile app --profile labeling up -d --wait label-stream

up-inference: stop-e2e  ## 啟動情緒推論（S4，需先在 .env 設 INFERENCE_MODEL_VERSION，模型放在 models/）
	$(COMPOSE) --profile app --profile inference up -d --wait inference

up-alerting: stop-e2e  ## 啟動熱度偵測與 Telegram bot（S5，需先在 .env 設 TELEGRAM_BOT_TOKEN）
	$(COMPOSE) --profile app --profile alerting up -d --wait heat bot

down:
	$(COMPOSE) --profile app --profile labeling --profile inference --profile alerting down --remove-orphans

stop-e2e:  ## e2e 環境運作中就先清掉（make e2e-down），避免開發環境沿用 e2e 的容器
	@if [ -n "$$($(E2E_RUNNING))" ]; then echo "e2e 環境運作中，先執行 make e2e-down"; $(MAKE) e2e-down; fi

stop-dev:  ## 開發環境運作中就先停掉（make down，不刪 volume），避免 e2e 沿用開發環境的容器
	@if [ -z "$$($(E2E_RUNNING))" ] && [ -n "$$(docker ps -aq --filter label=com.docker.compose.project=radar)" ]; then \
		echo "開發環境運作中，先執行 make down（不刪 volume）"; $(MAKE) down; fi

e2e-down:  ## 停止 e2e 環境並刪除 e2e 專用的資料與 log volume（不碰開發環境的 volume）
	$(COMPOSE_E2E) --profile app down -v --remove-orphans

logs:
	$(COMPOSE) logs -f

migrate:
	$(UV_ENV) alembic upgrade head

topics:
	$(UV_ENV) python tools/create_topics.py

connector:  ## 註冊或更新 Debezium connector（冪等，需先 make migrate 建立 publication）
	$(UV_ENV) python tools/register_connector.py

ch-migrate:  ## 套用 ClickHouse 尚未執行的 migration
	$(UV_ENV) python tools/migrate_clickhouse.py

seed:  ## 透過 API 建立初始看板（需先 make api）
	$(UV_ENV) python tools/seed_boards.py

testset:  ## 依看板配額抽出 300 篇人工測試集（S3-04，只能抽一次；配額見開發規格 7.11）
	$(UV_ENV) python -m radar.ml.labeling.testset --counts Gossiping=180 Stock=90 Tech_Job=30

human-label:  ## 本機人工標註頁（http://127.0.0.1:8090）
	$(UV_ENV) python -m radar.ml.labeling.human_app

api:  ## 本機啟動管理 API（http://localhost:8000/docs）
	$(UV_ENV) uvicorn radar.api.main:app --reload --port 8000

setup:  ## 本機建立 .venv 與相依（check_env.py setup 會呼叫；worktree 共用主目錄的 .venv）
	uv sync

ci-setup:  ## CI 安裝相依
	pip install -q pre-commit==$(PRE_COMMIT_VERSION)
	uv sync --dev

check:  ## lint + 不需要容器的測試（CI 每個 PR 都跑）
	pre-commit run --all-files
	uv run pytest tests/unit

coverage:  ## 單元 + 整合測試的覆蓋率（只在 CI 用，compose 的服務由 CI 先開好；IT_* 見 ci.yml），Cobertura XML 寫到 coverage-reports/
	uv run pytest tests/unit tests/integration -n auto --dist loadgroup --durations=15 --cov=src/radar --cov-report=xml:coverage-reports/python.xml -q

lint:
	uv run ruff check .
	uv run ruff format --check .
	pre-commit run bandit --all-files

test:
	uv run pytest tests/unit

test-int:  ## 整合測試（compose 的 test 服務；在主目錄跑，sandbox 內的 agent 改直接下 docker compose，見開發規格 7.26）
	docker compose -f compose.yaml --env-file .env run --rm test

e2e-up: stop-dev  ## 整套服務 + 假 PTT 伺服器，使用 e2e 專用的 volume（不碰開發資料、不連真的 PTT）；會先停掉開發環境（不刪 volume）
	$(COMPOSE_E2E) --profile app up -d --build --wait

e2e:  ## 端到端測試，需先 make e2e-up
	$(UV_ENV) pytest tests/e2e -m e2e
