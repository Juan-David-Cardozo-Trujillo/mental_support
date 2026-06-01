#!/bin/bash
#
# run-celery-worker.sh
# Start Celery worker for background task processing
#
# Usage:
#   ./run-celery-worker.sh [--concurrency=4] [--queue=default,email,reports]
#

set -e

export PYTHONPATH=/app:$PYTHONPATH

# Default settings
CONCURRENCY=${CONCURRENCY:-4}
QUEUES=${QUEUES:-default,email,reports}
LOG_LEVEL=${LOG_LEVEL:-info}

echo "🚀 Starting Celery Worker..."
echo "   Concurrency: $CONCURRENCY workers"
echo "   Queues: $QUEUES"
echo "   Log Level: $LOG_LEVEL"

celery -A backend.tasks.celery_app worker \
  --loglevel=$LOG_LEVEL \
  --concurrency=$CONCURRENCY \
  -Q $QUEUES \
  --max-tasks-per-child=1000 \
  --time-limit=3600 \
  --soft-time-limit=3000 \
  --prefetch-multiplier=4 \
  -n worker@%h
