FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 先只裝相依套件，原始碼變動時可沿用這層快取；lib/ 內有本地 wheel
COPY pyproject.toml uv.lock ./
COPY lib/ lib/
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
COPY alembic.ini ./
COPY infra/postgres/migrations/ infra/postgres/migrations/
COPY infra/kafka/topics.yaml infra/kafka/topics.yaml
COPY infra/clickhouse/migrations/ infra/clickhouse/migrations/
COPY infra/debezium/radar-cdc.json infra/debezium/radar-cdc.json
COPY scripts/ scripts/
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 radar && mkdir -p /app/log && chown radar /app/log
USER radar

# 各服務在 docker-compose 以 command 指定，例如 python -m radar.ingest.main
CMD ["python", "-c", "print('specify a command in docker-compose')"]
