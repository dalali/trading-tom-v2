#!/usr/bin/env bash
# Container entrypoint (architecture Section 8.1 startup sequence):
#   1. Run migrations (alembic upgrade head)
#   2. Seed the first admin if none exists (idempotent, logs+skips if
#      ADMIN_BOOTSTRAP_EMAIL/PASSWORD are unset)
#   3. Start uvicorn
set -euo pipefail

echo "Running migrations..."
alembic upgrade head

echo "Running admin bootstrap..."
python -m app.bootstrap_run

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
