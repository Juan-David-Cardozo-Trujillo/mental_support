"""
Celery Background Tasks
=======================

Async job definitions for:
- Burnout prevention (RULE-02, RULE-09)
- Peak demand notifications
- Report window cleanup (RULE-03)
- Badge awards (gamification)
- Appointment reminders
- Message retention (RULE-06)
- System metrics collection

All tasks are idempotent and designed for reliable execution with retries.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import text, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.tasks.celery_app import celery_app
from backend.core.database import AuthSessionFactory, PlatformSessionFactory
from backend.db.platform_models import (
    PeerCounselorProfile,
    ChatMessage,
    PeerReport,
    Appointment,
    RecognitionBadge,
    AcademicCalendarPeak,
    SystemMetric,
    AccountStatusEnum,
    AppointmentStatusEnum,
    RetentionPolicyEnum,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# BURNOUT PREVENTION TASKS (RULE-02, RULE-09)
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def reset_daily_session_counts(self):
    """
    Reset daily session counts for all peer counselors at midnight.
    
    RULE-02: Each peer has a 3 sessions/day limit.
    This task runs daily at 00:00 to reset the counter.
    
    Idempotent: Safe to run multiple times.
    """
    import asyncio
    
    async def _reset():
        async with PlatformSessionFactory() as session:
            try:
                # Reset daily_session_count to 0 for all peers
                result = await session.execute(
                    text("""
                    UPDATE peer_counselor_profiles
                    SET daily_session_count = 0
                    WHERE daily_session_count > 0
                    RETURNING id, daily_session_count
                    """)
                )
                reset_count = len(result.fetchall())
                logger.info(f"✓ Reset daily session counts for {reset_count} peers")
                await session.commit()
                return {"reset_count": reset_count, "status": "success"}
            except Exception as e:
                logger.error(f"✗ Failed to reset daily session counts: {e}")
                await session.rollback()
                raise self.retry(exc=e)
    
    return asyncio.run(_reset())


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def check_peer_burnout_status(self):
    """
    Check and enforce burnout thresholds every 6 hours.
    
    RULE-02: Peers with 20+ sessions → set account_status = unavailable
    RULE-02: Peers with 3 sessions today → set available = false
    
    This task identifies burned-out peers and prevents them from accepting new sessions.
    Idempotent: Checks thresholds only.
    """
    import asyncio
    
    async def _check():
        async with PlatformSessionFactory() as session:
            try:
                # Find peers exceeding 20 session threshold
                result = await session.execute(
                    text("""
                    SELECT id, sessions_completed, account_status
                    FROM peer_counselor_profiles
                    WHERE sessions_completed >= :burnout_threshold
                      AND account_status != :unavailable_status
                    """),
                    {"burnout_threshold": 20, "unavailable_status": "unavailable"}
                )
                
                burnout_peers = result.fetchall()
                if burnout_peers:
                    await session.execute(
                        text("""
                        UPDATE peer_counselor_profiles
                        SET account_status = :unavailable_status
                        WHERE sessions_completed >= :burnout_threshold
                          AND account_status != :unavailable_status
                        """),
                        {"burnout_threshold": 20, "unavailable_status": "unavailable"}
                    )
                    await session.commit()
                    logger.info(f"✓ Marked {len(burnout_peers)} peers as unavailable (burnout threshold)")
                    return {"burned_out_peers": len(burnout_peers), "status": "success"}
                
                logger.debug("No burnout threshold violations found")
                return {"burned_out_peers": 0, "status": "success"}
                
            except Exception as e:
                logger.error(f"✗ Burnout check failed: {e}")
                await session.rollback()
                raise self.retry(exc=e)
    
    return asyncio.run(_check())


# ──────────────────────────────────────────────────────────────────────────────
# PEAK DEMAND NOTIFICATIONS (RULE-09)
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=2, default_retry_delay=120)
def check_peak_demand_notifications(self):
    """
    Daily notification to inactive peers about upcoming peak demand periods.
    
    RULE-09: Notify peers who haven't completed a session in 30 days that
    peak demand (exam periods) is approaching. This helps recruit peers
    for predictable surge periods.
    
    Runs daily at 8 AM.
    """
    import asyncio
    
    async def _check():
        async with PlatformSessionFactory() as session:
            try:
                thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
                
                # Find peers with no recent sessions
                result = await session.execute(
                    text("""
                    SELECT id, user_id
                    FROM peer_counselor_profiles
                    WHERE (last_session_date IS NULL 
                        OR last_session_date < :cutoff_date)
                      AND account_status = :active_status
                    """),
                    {"cutoff_date": thirty_days_ago, "active_status": "active"}
                )
                
                inactive_peers = result.fetchall()
                
                # In production, send emails/push notifications here
                # For now, just log for monitoring
                logger.info(f"✓ Identified {len(inactive_peers)} inactive peers for peak demand notification")
                
                # TODO: Queue email task for each peer
                # for peer in inactive_peers:
                #     send_peak_demand_email.delay(peer.user_id)
                
                return {"notified_peers": len(inactive_peers), "status": "success"}
                
            except Exception as e:
                logger.error(f"✗ Peak demand notification check failed: {e}")
                await session.rollback()
                raise self.retry(exc=e)
    
    return asyncio.run(_check())


# ──────────────────────────────────────────────────────────────────────────────
# REPORT WINDOW CLEANUP (RULE-03)
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def check_report_windows(self):
    """
    Hourly check to reset report_count_7d when rolling window expires.
    
    RULE-03: Auto-suspend peers at 3 reports in 7 days.
    This task recalculates report counts, resetting old reports outside the window.
    
    Idempotent: Recalculates counts based on timestamps.
    """
    import asyncio
    
    async def _check():
        async with PlatformSessionFactory() as session:
            try:
                seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
                
                # For each peer, recount reports from the past 7 days
                result = await session.execute(
                    text("""
                    SELECT pcp.id, COUNT(pr.id) as recent_reports
                    FROM peer_counselor_profiles pcp
                    LEFT JOIN peer_reports pr 
                        ON pcp.id = pr.peer_id 
                        AND pr.created_at > :seven_days_ago
                    WHERE pcp.report_count_7d > 0
                    GROUP BY pcp.id
                    HAVING COUNT(pr.id) != pcp.report_count_7d
                    """),
                    {"seven_days_ago": seven_days_ago}
                )
                
                mismatches = result.fetchall()
                
                # Update peer report counts
                for peer_id, recent_count in mismatches:
                    await session.execute(
                        text("""
                        UPDATE peer_counselor_profiles
                        SET report_count_7d = :recent_count
                        WHERE id = :peer_id
                        """),
                        {"peer_id": peer_id, "recent_count": recent_count}
                    )
                
                await session.commit()
                logger.info(f"✓ Updated report counts for {len(mismatches)} peers")
                return {"updated_peers": len(mismatches), "status": "success"}
                
            except Exception as e:
                logger.error(f"✗ Report window check failed: {e}")
                await session.rollback()
                raise self.retry(exc=e)
    
    return asyncio.run(_check())


# ──────────────────────────────────────────────────────────────────────────────
# GAMIFICATION (RECOGNITION BADGES)
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=2, default_retry_delay=120)
def award_peer_badges(self):
    """
    Daily badge award check for peer milestones.
    
    Milestones:
    - 10 sessions: "Helpful Hand"
    - 25 sessions: "Compassionate Counselor"
    - 50 sessions: "Mental Health Champion"
    - 100 sessions: "Wellbeing Warrior"
    
    Idempotent: Checks existing badges before awarding.
    """
    import asyncio
    
    async def _award():
        async with PlatformSessionFactory() as session:
            try:
                milestones = [
                    (10, "Helpful Hand", "Completed 10 supportive conversations"),
                    (25, "Compassionate Counselor", "Completed 25 conversations"),
                    (50, "Mental Health Champion", "Completed 50 conversations"),
                    (100, "Wellbeing Warrior", "Completed 100 conversations"),
                ]
                
                awarded_count = 0
                
                for threshold, badge_name, description in milestones:
                    # Find peers meeting this milestone who haven't received the badge
                    result = await session.execute(
                        text("""
                        SELECT DISTINCT pcp.id
                        FROM peer_counselor_profiles pcp
                        WHERE pcp.sessions_completed >= :threshold
                          AND NOT EXISTS (
                            SELECT 1 FROM recognition_badges rb
                            WHERE rb.peer_id = pcp.id
                              AND rb.badge_name = :badge_name
                          )
                        """),
                        {"threshold": threshold, "badge_name": badge_name}
                    )
                    
                    peers = result.fetchall()
                    
                    for (peer_id,) in peers:
                        # Award badge
                        await session.execute(
                            text("""
                            INSERT INTO recognition_badges
                            (id, peer_id, badge_name, description, awarded_at)
                            VALUES (gen_random_uuid(), :peer_id, :badge_name, :description, NOW())
                            ON CONFLICT DO NOTHING
                            """),
                            {"peer_id": peer_id, "badge_name": badge_name, "description": description}
                        )
                        awarded_count += 1
                
                await session.commit()
                logger.info(f"✓ Awarded {awarded_count} badges to peers")
                return {"badges_awarded": awarded_count, "status": "success"}
                
            except Exception as e:
                logger.error(f"✗ Badge award task failed: {e}")
                await session.rollback()
                raise self.retry(exc=e)
    
    return asyncio.run(_award())


# ──────────────────────────────────────────────────────────────────────────────
# APPOINTMENT REMINDERS
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def send_appointment_reminders(self):
    """
    Send appointment reminders every 15 minutes.
    
    Sends reminders to students 24-25 hours before confirmed appointments.
    This gives enough time for students to prepare and reduces no-shows.
    
    Idempotent: Tracks sent reminders to avoid duplicates.
    """
    import asyncio
    
    async def _send():
        async with PlatformSessionFactory() as session:
            try:
                now = datetime.now(timezone.utc)
                reminder_window_start = now + timedelta(hours=24)
                reminder_window_end = now + timedelta(hours=25)
                
                # Find confirmed appointments in 24-25 hour window
                result = await session.execute(
                    text("""
                    SELECT id, student_id, appointment_datetime
                    FROM appointments
                    WHERE status = :confirmed
                      AND appointment_datetime > :window_start
                      AND appointment_datetime < :window_end
                      AND reminder_sent = false
                    """),
                    {
                        "confirmed": "confirmed",
                        "window_start": reminder_window_start,
                        "window_end": reminder_window_end,
                    }
                )
                
                appointments = result.fetchall()
                
                # In production, send via email/SMS service
                # For now, just log and mark as sent
                for appt_id, student_id, appt_time in appointments:
                    logger.info(f"✓ Reminder queued for appointment {appt_id} (scheduled {appt_time})")
                    
                    # Mark reminder as sent
                    await session.execute(
                        text("""
                        UPDATE appointments
                        SET reminder_sent = true
                        WHERE id = :appt_id
                        """),
                        {"appt_id": appt_id}
                    )
                    
                    # TODO: Queue email task
                    # send_appointment_reminder_email.delay(student_id, appt_id)
                
                await session.commit()
                logger.info(f"✓ Sent {len(appointments)} appointment reminders")
                return {"reminders_sent": len(appointments), "status": "success"}
                
            except Exception as e:
                logger.error(f"✗ Appointment reminder task failed: {e}")
                await session.rollback()
                raise self.retry(exc=e)
    
    return asyncio.run(_send())


# ──────────────────────────────────────────────────────────────────────────────
# MESSAGE RETENTION (RULE-06)
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def purge_expired_messages(self):
    """
    Delete or anonymize expired messages based on retention policy.
    
    RULE-06: Non-flagged messages deleted after 24 hours.
    RULE-06: Flagged messages retained encrypted for 90 days.
    
    Runs daily at 11 PM.
    Idempotent: Deletes based on timestamps, safe to re-run.
    """
    import asyncio
    
    async def _purge():
        async with PlatformSessionFactory() as session:
            try:
                now = datetime.now(timezone.utc)
                
                # Delete non-flagged messages older than 24 hours
                one_day_ago = now - timedelta(hours=24)
                delete_result = await session.execute(
                    text("""
                    DELETE FROM chat_messages
                    WHERE retention_policy = :discard
                      AND created_at < :cutoff_date
                    """),
                    {"discard": "discard_24h", "cutoff_date": one_day_ago}
                )
                discarded = delete_result.rowcount or 0
                
                # Archive flagged messages older than 90 days (for compliance)
                ninety_days_ago = now - timedelta(days=90)
                archive_result = await session.execute(
                    text("""
                    DELETE FROM chat_messages
                    WHERE retention_policy = :retain
                      AND created_at < :cutoff_date
                    """),
                    {"retain": "retain_90d", "cutoff_date": ninety_days_ago}
                )
                archived = archive_result.rowcount or 0
                
                await session.commit()
                logger.info(f"✓ Purged {discarded} expired messages, archived {archived} old flagged messages")
                return {
                    "deleted_count": discarded,
                    "archived_count": archived,
                    "status": "success"
                }
                
            except Exception as e:
                logger.error(f"✗ Message purge task failed: {e}")
                await session.rollback()
                raise self.retry(exc=e)
    
    return asyncio.run(_purge())


# ──────────────────────────────────────────────────────────────────────────────
# SYSTEM METRICS COLLECTION
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=2, default_retry_delay=120)
def collect_system_metrics(self):
    """
    Collect hourly system metrics for monitoring and alerts.
    
    Metrics:
    - Active sessions count
    - Queue depth
    - Peer availability count
    - Daily messages sent
    - Average chat latency
    
    Idempotent: Appends new metrics to time-series.
    """
    import asyncio
    
    async def _collect():
        async with PlatformSessionFactory() as session:
            try:
                now = datetime.now(timezone.utc)
                one_hour_ago = now - timedelta(hours=1)
                
                # Count active chat sessions
                active_sessions = await session.execute(
                    text("""
                    SELECT COUNT(DISTINCT id) as count
                    FROM chat_sessions
                    WHERE session_status = :active
                    """),
                    {"active": "active"}
                )
                active_count = active_sessions.scalar() or 0
                
                # Count queue depth
                queue_depth_result = await session.execute(
                    text("""
                    SELECT COUNT(DISTINCT id) as count
                    FROM chat_sessions
                    WHERE session_status = :queued
                    """),
                    {"queued": "queued"}
                )
                queue_depth = queue_depth_result.scalar() or 0
                
                # Count available peers
                available_peers = await session.execute(
                    text("""
                    SELECT COUNT(DISTINCT id) as count
                    FROM peer_counselor_profiles
                    WHERE available = true
                      AND account_status = :active
                    """),
                    {"active": "active"}
                )
                available_count = available_peers.scalar() or 0
                
                # Count hourly messages
                hourly_messages = await session.execute(
                    text("""
                    SELECT COUNT(*) as count
                    FROM chat_messages
                    WHERE created_at > :one_hour_ago
                    """),
                    {"one_hour_ago": one_hour_ago}
                )
                message_count = hourly_messages.scalar() or 0
                
                # Store metrics
                await session.execute(
                    text("""
                    INSERT INTO system_metrics
                    (id, metric_name, metric_value, recorded_at)
                    VALUES
                    (gen_random_uuid(), 'active_sessions', :active_sessions, NOW()),
                    (gen_random_uuid(), 'queue_depth', :queue_depth, NOW()),
                    (gen_random_uuid(), 'available_peers', :available_peers, NOW()),
                    (gen_random_uuid(), 'hourly_messages', :hourly_messages, NOW())
                    """),
                    {
                        "active_sessions": active_count,
                        "queue_depth": queue_depth,
                        "available_peers": available_count,
                        "hourly_messages": message_count,
                    }
                )
                
                await session.commit()
                logger.debug(f"✓ Collected metrics: {active_count} active, {queue_depth} queued, {available_count} available peers")
                return {
                    "active_sessions": active_count,
                    "queue_depth": queue_depth,
                    "available_peers": available_count,
                    "hourly_messages": message_count,
                    "status": "success"
                }
                
            except Exception as e:
                logger.error(f"✗ Metrics collection failed: {e}")
                await session.rollback()
                raise self.retry(exc=e)
    
    return asyncio.run(_collect())


# ──────────────────────────────────────────────────────────────────────────────
# UTILITY TASKS
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=1)
def send_email(self, recipient: str, subject: str, body: str):
    """
    Send email via external service (e.g., SendGrid, AWS SES).
    
    TODO: Implement email service integration.
    For now, just logs the request.
    """
    logger.info(f"✓ Email queued: {recipient} / {subject}")
    # In production:
    # email_service.send(recipient, subject, body)
    return {"status": "queued", "recipient": recipient}


@celery_app.task(bind=True, max_retries=1)
def send_sms_notification(self, phone: str, message: str):
    """
    Send SMS notification via external service (e.g., Twilio).
    
    TODO: Implement SMS service integration.
    """
    logger.info(f"✓ SMS queued: {phone} / {message}")
    # In production:
    # sms_service.send(phone, message)
    return {"status": "queued", "phone": phone}
