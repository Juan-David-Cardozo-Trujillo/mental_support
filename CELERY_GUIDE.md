# Celery Background Tasks — Setup & Usage Guide

## Overview

**Celery** is the asynchronous task queue for the Mental Health Platform. It processes background jobs that shouldn't block the main API, such as:

- Burnout detection & peer suspension (RULE-02)
- Report window management (RULE-03)
- Peak demand notifications (RULE-09)
- Message retention purging (RULE-06)
- Badge awards & gamification
- Appointment reminders
- System metrics collection

## Architecture

```
┌─────────────────┐
│  FastAPI App    │   (Main API server)
│  (Port 8000)    │───┐
└─────────────────┘   │
                      │ queue task
                      ▼
                 ┌─────────────┐
                 │    REDIS    │   (Message broker + results store)
                 │ (Port 6379) │
                 └──────┬──────┘
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌──────────┐
    │ Worker  │    │ Worker  │    │   Beat   │
    │    1    │    │    2    │    │Scheduler │
    └────┬────┘    └────┬────┘    └────┬─────┘
         │              │              │
         └──────────────┴──────────────┘
                   │
            ┌──────▼───────┐
            │ PostgreSQL   │
            │  (Database)  │
            └──────────────┘
```

## Quick Start (Docker)

The docker-compose.yml includes Celery services. Start the full stack:

```bash
docker-compose up -d
```

This starts:

- ✅ `celery_worker` — Task executor (1 worker, 4 concurrent tasks)
- ✅ `celery_beat` — Periodic task scheduler
- ✅ `backend` — FastAPI app (can queue tasks)

## Running Celery Locally (Development)

### 1. Terminal 1: Celery Worker

```bash
cd backend
celery -A tasks.celery_app worker --loglevel=info --concurrency=4
```

Output:

```
 ---------- celery@MACHINE v5.4.0
 --------- tasks pool: prefork @ 4 concurrency
 [tasks]
   . backend.tasks.celery_tasks.reset_daily_session_counts
   . backend.tasks.celery_tasks.check_peer_burnout_status
   ... (8 tasks registered)
 [2026-05-31 10:15:23,456: INFO/MainProcess] celery worker ready.
```

### 2. Terminal 2: Celery Beat (Scheduler)

```bash
cd backend
celery -A tasks.celery_app beat --loglevel=info
```

Output:

```
celery beat v5.4.0
Scheduler: celery.beat:SchedulingError
 [...]
 [2026-05-31 10:15:30,123: INFO/MainProcess] Scheduler: Sending due task reset-daily-session-counts
```

### 3. Terminal 3: Flower (Monitoring UI)

```bash
cd backend
flower -A tasks.celery_app
```

Visit: **http://localhost:5555**

Flower shows:

- ✅ Task execution history
- ✅ Worker status & health
- ✅ Queue depth
- ✅ Real-time task execution

## Task Reference

### RULE-02: Burnout Prevention

#### `reset_daily_session_counts()`

- **Schedule**: Daily at 00:00 (midnight)
- **Action**: Reset `daily_session_count = 0` for all peers
- **Why**: Each peer has 3 sessions/day cap; counter resets daily

#### `check_peer_burnout_status()`

- **Schedule**: Every 6 hours
- **Action**: Check peers with `sessions_completed >= 20`; set `account_status = unavailable`
- **Why**: Prevents peer burnout; peers with 20+ sessions must take break

### RULE-03: Report Window Management

#### `check_report_windows()`

- **Schedule**: Every 1 hour
- **Action**: Recalculate `report_count_7d` for each peer (reports older than 7 days excluded)
- **Why**: RULE-03 requires rolling 7-day window; old reports fall off after 7 days

### RULE-06: Message Retention

#### `purge_expired_messages()`

- **Schedule**: Daily at 23:00
- **Action**:
  - Delete non-flagged messages older than 24 hours
  - Delete flagged messages older than 90 days (compliance archive)
- **Why**: Privacy policy; non-flagged messages deleted quickly; flagged retained for investigation

### RULE-09: Peak Demand Management

#### `check_peak_demand_notifications()`

- **Schedule**: Daily at 08:00
- **Action**: Identify peers inactive 30+ days; queue notification about upcoming peak periods
- **Why**: Recruit peers for predictable surge periods (exams, etc.)

### Gamification

#### `award_peer_badges()`

- **Schedule**: Daily at 06:00
- **Action**: Award badges at milestones:
  - 10 sessions: "Helpful Hand"
  - 25 sessions: "Compassionate Counselor"
  - 50 sessions: "Mental Health Champion"
  - 100 sessions: "Wellbeing Warrior"
- **Why**: Recognize peer contributions; drive engagement

### Notifications

#### `send_appointment_reminders()`

- **Schedule**: Every 15 minutes
- **Action**: Find appointments in 24-25 hour window; queue reminder notifications
- **Why**: Reduce no-shows; gives students 24h notice

### Monitoring

#### `collect_system_metrics()`

- **Schedule**: Every 1 hour
- **Action**: Record to `system_metrics` table:
  - Active sessions count
  - Queue depth
  - Available peers count
  - Hourly messages sent
- **Why**: Historical metrics for dashboards, alerting, capacity planning

## Queuing Tasks from FastAPI

### Manual Task Queue (in route handlers)

```python
from backend.tasks.celery_app import celery_app

@router.post("/match-request")
async def match_request(db: AsyncSession):
    # Do something...

    # Queue a task (async, non-blocking)
    result = celery_app.send_task(
        'backend.tasks.celery_tasks.send_email',
        kwargs={
            'recipient': student.email,
            'subject': 'Match Found!',
            'body': 'You have been matched with a peer counselor.'
        }
    )

    return {"task_id": result.id}
```

### Check Task Status

```python
from backend.tasks.celery_app import celery_app

# Get task result
task_id = "abc-123-def"
result = celery_app.AsyncResult(task_id)

if result.ready():
    print(f"Task result: {result.result}")
else:
    print(f"Task status: {result.status}")  # PENDING, STARTED, SUCCESS, FAILURE
```

## Configuration

All settings in `backend/tasks/celery_app.py`:

| Setting                      | Default                    | Description                          |
| ---------------------------- | -------------------------- | ------------------------------------ |
| `CELERY_BROKER_URL`          | `redis://localhost:6379/1` | Message broker (Redis db 1)          |
| `CELERY_RESULT_BACKEND`      | `redis://localhost:6379/2` | Result storage (Redis db 2)          |
| `task_serializer`            | `json`                     | Task message format                  |
| `timezone`                   | `America/Bogota`           | Scheduler timezone                   |
| `task_acks_late`             | `True`                     | Don't ack task until completed       |
| `task_reject_on_worker_lost` | `True`                     | Retry if worker dies                 |
| `worker_max_tasks_per_child` | `1000`                     | Recycle process after 1000 tasks     |
| `result_expires`             | `3600`                     | Keep results 1 hour after completion |

## Deployment (Production)

### AWS ECS with Celery

**Task Definition** (`celery_worker`):

```json
{
  "name": "celery_worker",
  "image": "myregistry/mindbridge:backend-latest",
  "command": ["celery", "-A", "tasks.celery_app", "worker", "--loglevel=info"],
  "memory": 512,
  "cpu": 256,
  "environment": [
    { "name": "CELERY_BROKER_URL", "value": "redis://elasticache:6379/1" },
    { "name": "CELERY_RESULT_BACKEND", "value": "redis://elasticache:6379/2" }
  ]
}
```

**Scaling**:

- 1-2 workers for development
- 4-8 workers for production (scale based on queue depth)
- Beat scheduler (1 instance only; don't scale)

### Health Checks

```bash
# Check Celery worker health
celery -A tasks.celery_app inspect active

# Check scheduled tasks
celery -A tasks.celery_app inspect scheduled

# Monitor queue depth
redis-cli -n 1 LLEN celery
```

## Troubleshooting

### Tasks Not Running

1. Check worker is running: `celery -A tasks.celery_app inspect active`
2. Check Redis connection: `redis-cli ping`
3. Check task is registered: `celery -A tasks.celery_app inspect registered`
4. Check worker logs: `celery -A tasks.celery_app worker --loglevel=debug`

### Task Stuck in PENDING

Task is queued but not picked up by any worker.

```bash
# Increase concurrency
celery -A tasks.celery_app worker --concurrency=8

# Check for exceptions
celery -A tasks.celery_app worker --loglevel=debug
```

### Redis Connection Error

```bash
# Verify Redis running
redis-cli ping
# Expected output: PONG

# Check CELERY_BROKER_URL in .env
cat .env | grep CELERY
```

### Celery Beat Not Firing Tasks

1. Ensure only 1 beat instance running (critical!)
2. Check beat logs: `celery -A tasks.celery_app beat --loglevel=debug`
3. Verify timezone matches your location: `celery -A tasks.celery_app inspect active_queues`

## Monitoring & Alerts

### Flower Dashboard

Visit **http://localhost:5555**:

- **Workers**: Active worker instances
- **Task History**: Execution times, success/failure rates
- **Queues**: Task queue depth
- **Stats**: Memory usage, task throughput

### CloudWatch Metrics (Production)

```python
# Custom metrics in task code
import boto3
cloudwatch = boto3.client('cloudwatch')
cloudwatch.put_metric_data(
    Namespace='MindBridge',
    MetricData=[
        {'MetricName': 'TaskCount', 'Value': 42, 'Unit': 'Count'},
    ]
)
```

### Alerting Rules

```
ALERT HighQueueDepth
  if celery_queue_length > 100 for 5m

ALERT WorkerDown
  if celery_worker_count < 2 for 10m

ALERT TaskFailureRate
  if celery_task_failures / celery_task_total > 0.05
```

## Best Practices

✅ **DO**:

- Make tasks idempotent (safe to retry)
- Use task timeouts to prevent hangs
- Log task execution with context
- Monitor queue depth
- Scale workers based on load

❌ **DON'T**:

- Store large data in task kwargs (use IDs, fetch from DB)
- Run long-running tasks in beat (use worker)
- Scale beat horizontally (only 1 instance allowed)
- Ignore task failures (set up alerting)

## References

- Celery Documentation: https://docs.celeryproject.org/
- Flower (Monitoring): https://flower.readthedocs.io/
- Redis Broker: https://docs.celeryproject.org/en/stable/brokers/redis.html

---

**Next Steps**:

1. ✅ Review scheduled tasks in `celery_app.py`
2. ✅ Start worker + beat locally to test
3. ✅ Monitor with Flower
4. ✅ Add custom tasks as needed
5. ✅ Deploy to staging, then production
