#!/bin/sh
set -e

# The API container owns the schema; the worker just waits for it.
if [ "$1" = "api" ]; then
    echo "running migrations..."
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
elif [ "$1" = "worker" ]; then
    exec python -m app.worker
else
    exec "$@"
fi
