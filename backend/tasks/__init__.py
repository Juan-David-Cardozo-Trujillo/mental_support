"""
Celery Tasks Package

Import and expose Celery app for background task execution.
"""

from backend.tasks.celery_app import celery_app

__all__ = ["celery_app"]
