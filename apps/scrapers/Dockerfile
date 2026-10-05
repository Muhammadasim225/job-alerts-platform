# Build context is the repo root (the scraper depends on packages/shared):
#   docker compose build scraper-worker
FROM python:3.12-slim

# Tesseract for scanned PDFs and image adverts
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    OMP_THREAD_LIMIT=1 \
    PATH="/app/apps/scrapers/.venv/bin:$PATH"

# Same relative layout as the repo, so the "../../packages/shared" path source resolves
COPY packages/shared /app/packages/shared
WORKDIR /app/apps/scrapers
COPY apps/scrapers/pyproject.toml apps/scrapers/uv.lock ./
# The uv cache persists between builds, so a dependency change does not re-download everything
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY apps/scrapers/ ./

# Default: Celery worker. Beat and migrations run from the same image with other commands.
# OMP_THREAD_LIMIT=1: one Tesseract = one core; parallelism comes from Celery processes
# (several OCR jobs at once), not from threads fighting over the same cores.
CMD ["celery", "-A", "celery_app", "worker", "-Q", "scrape,process,default", "--loglevel=INFO", "--concurrency=4"]
