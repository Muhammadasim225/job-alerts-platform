# Build context is the repo root (the API depends on packages/shared):
#   docker compose build api
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/apps/api/.venv/bin:$PATH"

COPY packages/shared /app/packages/shared
WORKDIR /app/apps/api
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY apps/api/ ./

# Least privilege: the API only reads/writes the database, it needs no root
RUN useradd --system --uid 10001 api
USER api

EXPOSE 8000
# Workers: one per core is a good start; set API_WORKERS in .env to tune
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-2} --proxy-headers"]
