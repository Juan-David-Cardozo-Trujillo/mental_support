"""
Celery Application Configuration
==================================

Configured with Redis broker (db 1) and result backend (db 2).

Usage:
    celery -A backend.tasks.celery_app worker --loglevel=info
    celery -A backend.tasks.celery_app beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab
from backend.core.config import settings

# ──────────────────────────────────────────────────────────────────────────────
# Celery App Instance
# ──────────────────────────────────────────────────────────────────────────────

celery_app = Celery(
    "mindbridge_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Bogota",  # Colombia timezone
    enable_utc=True,
    
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=1000,
    
    # Result backend
    result_expires=3600,  # 1 hour
    result_extended=True,
    
    # Beat schedule (periodic tasks)
    beat_schedule={
        # ── Burnout Prevention (RULE-02, RULE-09) ────────────────────────────
        "reset-daily-session-counts": {
            "task": "backend.tasks.celery_tasks.reset_daily_session_counts",
            "schedule": crontab(hour=0, minute=0),  # Daily at midnight
            "options": {"queue": "default"},
        },
        "check-peer-burnout-status": {
            "task": "backend.tasks.celery_tasks.check_peer_burnout_status",
            "schedule": crontab(hour="*/6"),  # Every 6 hours
            "options": {"queue": "default"},
        },
        
        # ── Peak Demand Management (RULE-09) ────────────────────────────────
        "check-peak-demand-notifications": {
            "task": "backend.tasks.celery_tasks.check_peak_demand_notifications",
            "schedule": crontab(hour=8, minute=0),  # Daily at 8 AM
            "options": {"queue": "default"},
        },
        
        # ── Report Window Management (RULE-03) ────────────────────────────
        "check-report-windows": {
            "task": "backend.tasks.celery_tasks.check_report_windows",
            "schedule": crontab(minute=0),  # Every hour
            "options": {"queue": "default"},
        },
        
        # ── Gamification (Recognition) ───────────────────────────────────
        "award-peer-badges": {
            "task": "backend.tasks.celery_tasks.award_peer_badges",
            "schedule": crontab(hour=6, minute=0),  # Daily at 6 AM
            "options": {"queue": "default"},
        },
        
        # ── Appointment Reminders ────────────────────────────────────────
        "send-appointment-reminders": {
            "task": "backend.tasks.celery_tasks.send_appointment_reminders",
            "schedule": crontab(minute="*/15"),  # Every 15 minutes
            "options": {"queue": "default"},
        },
        
        # ── Message Retention (RULE-06) ──────────────────────────────────
        "purge-expired-messages": {
            "task": "backend.tasks.celery_tasks.purge_expired_messages",
            "schedule": crontab(hour=23, minute=0),  # Daily at 11 PM
            "options": {"queue": "default"},
        },
        
        # ── Monitoring & Metrics ────────────────────────────────────────
        "collect-system-metrics": {
            "task": "backend.tasks.celery_tasks.collect_system_metrics",
            "schedule": crontab(minute=0),  # Every hour
            "options": {"queue": "default"},
        },
    },
    
    # Queue configuration
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "email": {"exchange": "email", "routing_key": "email"},
        "reports": {"exchange": "reports", "routing_key": "reports"},
    },
    
    # Worker settings
    worker_prefetch_multiplier=4,
    worker_max_cached_per_worker=1000,
)

# Auto-discover tasks from backend.tasks.celery_tasks
celery_app.autodiscover_tasks(["backend.tasks"])
