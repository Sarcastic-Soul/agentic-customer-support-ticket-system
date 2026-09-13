# Same image serves both the api and worker containers (see
# docker-compose.yml's "app" profile) - only the command differs.

FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

# Dependencies first, in their own layer - only re-resolves when
# pyproject.toml/uv.lock change, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"

COPY --from=builder /app /app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
