# Build context is the repo root (the notifier depends on packages/shared):
#   docker compose build notifier
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/apps/notifier/.venv/bin:$PATH"

COPY packages/shared /app/packages/shared
WORKDIR /app/apps/notifier
COPY apps/notifier/pyproject.toml apps/notifier/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY apps/notifier/ ./

# Least privilege: the notifier only talks to Postgres, Redis, SMTP and push services
RUN useradd --system --uid 10002 notifier
USER notifier

# Network-bound work (SMTP, push services): a thread pool is enough and light
CMD ["sh", "-c", "celery -A celery_app worker -Q notify --pool=threads --concurrency=${NOTIFY_CONCURRENCY:-8} --hostname=notifier@%h --loglevel=INFO"]
