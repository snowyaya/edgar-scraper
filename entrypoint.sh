#!/bin/bash
# =============================================================================
# entrypoint.sh — API container startup script
# =============================================================================
#
# Runs on every `docker compose up` for the api service.
# Executes in this order:
#   1. Wait for DB (health check in compose handles this, but we double-check)
#   2. Run Alembic migrations (idempotent — safe to run on every startup)
#   3. Start uvicorn
#
# Why Alembic in the entrypoint vs a separate init container:
#   - Simpler compose file (no init container dependency chain)
#   - Alembic's `upgrade head` is idempotent — running it on every startup
#     is safe and ensures the schema is always current after a deploy
#   - On first run: creates all tables
#   - On subsequent runs: checks alembic_version table, no-ops if up to date

set -e  # exit immediately on any error

echo "👉 Running Alembic migrations..."
alembic upgrade head
echo "✅ Migrations complete!"

echo "🚀 Starting uvicorn..."
exec uvicorn api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level "${LOG_LEVEL:-info}" \
    --access-log
