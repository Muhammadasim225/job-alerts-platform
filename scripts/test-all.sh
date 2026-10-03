#!/usr/bin/env bash
# Run every Python test suite; exits non-zero if any suite fails.
#   bash scripts/test-all.sh
# The shared and api suites need the local Postgres container: docker compose up -d postgres
set -uo pipefail
cd "$(dirname "$0")/.."

status=0
for dir in apps/scrapers packages/shared apps/api; do
  echo "== $dir"
  (cd "$dir" && uv run pytest -q) || status=1
done

if [ "$status" -eq 0 ]; then echo "ALL SUITES PASSED"; else echo "SOME SUITES FAILED"; fi
exit "$status"
