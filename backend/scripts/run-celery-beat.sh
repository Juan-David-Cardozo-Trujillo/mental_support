#!/bin/bash
#
# run-celery-beat.sh
# Start Celery Beat scheduler for periodic tasks
#
# Usage:
#   ./run-celery-beat.sh
#
# Beat will execute scheduled tasks according to the schedule defined in:
#   backend/tasks/celery_app.py (beat_schedule)
#
# Scheduled tasks:
#   - reset-daily-session-counts          (daily 00:00)
#   - check-peer-burnout-status           (every 6 hours)
#   - check-peak-demand-notifications     (daily 08:00)
#   - check-report-windows                (every 1 hour)
#   - award-peer-badges                   (daily 06:00)
#   - send-appointment-reminders          (every 15 min)
#   - purge-expired-messages              (daily 23:00)
#   - collect-system-metrics              (every 1 hour)
#

set -e

export PYTHONPATH=/app:$PYTHONPATH

LOG_LEVEL=${LOG_LEVEL:-info}
SCHEDULER=${SCHEDULER:-celery.beat:PersistentScheduler}

echo "⏰ Starting Celery Beat Scheduler..."
echo "   Log Level: $LOG_LEVEL"
echo "   Scheduler: $SCHEDULER"
echo ""
echo "📅 Scheduled Tasks:"
echo "   ✓ reset-daily-session-counts          @ 00:00 (RULE-02)"
echo "   ✓ check-peer-burnout-status           @ */6h (RULE-02)"
echo "   ✓ check-peak-demand-notifications     @ 08:00 (RULE-09)"
echo "   ✓ check-report-windows                @ */1h (RULE-03)"
echo "   ✓ award-peer-badges                   @ 06:00 (Gamification)"
echo "   ✓ send-appointment-reminders          @ */15m (Notifications)"
echo "   ✓ purge-expired-messages              @ 23:00 (RULE-06)"
echo "   ✓ collect-system-metrics              @ */1h (Monitoring)"

celery -A backend.tasks.celery_app beat \
  --loglevel=$LOG_LEVEL \
  --scheduler=$SCHEDULER \
  --logfile=- \
  -n beat@%h
