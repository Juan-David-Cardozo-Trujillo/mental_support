#!/bin/bash
#
# run-celery-flower.sh
# Start Flower - Real-time Celery monitoring tool
#
# Web UI: http://localhost:5555
#
# Usage:
#   ./run-celery-flower.sh [--port=5555]
#

set -e

export PYTHONPATH=/app:$PYTHONPATH

PORT=${PORT:-5555}
BROKER=${CELERY_BROKER_URL:-redis://localhost:6379/1}

echo "🌸 Starting Flower (Celery Monitoring)..."
echo "   Broker: $BROKER"
echo "   Web UI: http://localhost:$PORT"
echo ""
echo "📊 Available Metrics:"
echo "   ✓ Task execution history"
echo "   ✓ Worker status & health"
echo "   ✓ Task queue depth"
echo "   ✓ Execution time distribution"
echo "   ✓ Task failure tracking"
echo "   ✓ Real-time task execution"

flower -A backend.tasks.celery_app \
  --broker=$BROKER \
  --port=$PORT \
  --loglevel=info \
  --persistent=True \
  --db=/tmp/flower_persistent_db
