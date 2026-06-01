"""Matching engine router — pairs students with peer counselors."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from redis.asyncio import Redis
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_platform_db
from backend.core.security import consent_required, get_current_user
from backend.db.platform_models import (
    ChatSession,
    PeerCounselorProfile,
    NeedsAssessmentResponse,
    AccountStatusEnum,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/matching", tags=["Matching"])


# ── Configuration ─────────────────────────────────────────────────────────────

BURNOUT_THRESHOLD = 20  # Sessions threshold for burnout (RULE-02)
DAILY_SESSION_CAP = 3  # Max sessions per day per peer (RULE-02, RULE-09)
MAX_QUEUE_WAIT_MINUTES = 15  # RULE-04: notify if > 15 min wait


# ── Models ────────────────────────────────────────────────────────────────────

class MatchingResponse(dict):
    """Response from POST /matching/request."""
    status: str  # 'matched' | 'queued'
    session_id: str | None  # if matched
    queue_position: int | None  # if queued
    estimated_wait_minutes: int | None  # if queued
    message: str


class QueueStatusResponse(dict):
    """Response from GET /matching/queue-status."""
    position: int
    estimated_wait_minutes: int


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_available_peers(db: AsyncSession) -> list[PeerCounselorProfile]:
    """
    RULE-04: Query available peer counselors ordered by lowest sessions_completed first.
    
    Criteria:
    - account_status = 'active'
    - available = true
    - daily_session_count < 3 (within daily cap)
    - sessions_completed < BURNOUT_THRESHOLD
    - report_count_7d < 3 (not under suspension)
    """
    stmt = (
        select(PeerCounselorProfile)
        .where(
            and_(
                PeerCounselorProfile.account_status == AccountStatusEnum.active,
                PeerCounselorProfile.available == True,
                PeerCounselorProfile.daily_session_count < DAILY_SESSION_CAP,
                PeerCounselorProfile.sessions_completed < BURNOUT_THRESHOLD,
                PeerCounselorProfile.report_count_7d < 3,
            )
        )
        .order_by(PeerCounselorProfile.sessions_completed.asc())  # lowest load first
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def _enqueue_student(redis: Redis, student_profile_id: str) -> tuple[int, int]:
    """
    Add student to matching queue in Redis.
    
    Redis key: matching_queue (sorted set)
    Score: timestamp (for FIFO ordering within priority)
    Value: student_profile_id
    
    Returns: (queue_position, estimated_wait_minutes)
    """
    now = datetime.now(tz=timezone.utc).timestamp()
    
    # Add to queue
    queue_key = "matching_queue"
    await redis.zadd(queue_key, {student_profile_id: now})
    
    # Get position (0-indexed)
    rank = await redis.zrank(queue_key, student_profile_id)
    position = rank + 1 if rank is not None else -1
    
    # Estimate wait: assume ~5 min per student at queue
    # This is a heuristic; production would use historical data
    estimated_wait = max(5, position * 5)
    
    # Set expiry: 1 hour (if student doesn't match, they're purged)
    await redis.expire(queue_key, 3600)
    
    return position, estimated_wait


async def _remove_from_queue(redis: Redis, student_profile_id: str) -> None:
    """Remove student from matching queue."""
    await redis.zrem("matching_queue", student_profile_id)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/request")
async def request_match(
    request: Request,
    user: dict = Depends(consent_required),
    db: AsyncSession = Depends(get_platform_db),
) -> MatchingResponse:
    """
    Request a match with an available peer counselor.
    
    RULE-04: Matching algorithm:
    1. Query available peer counselors (ordered by sessions_completed ASC)
    2. If any available: assign to lowest-load peer, create ChatSession, return session_id
    3. If none available: enqueue in Redis, return queue position + estimated wait
    4. If queue wait exceeds 15 min: send proactive notification + offer Resource Library
    
    Returns:
    {
        status: 'matched' | 'queued',
        session_id: UUID | null,
        queue_position: int | null,
        estimated_wait_minutes: int | null,
        message: string
    }
    """
    student_profile_id = UUID(user.get("sub"))
    redis: Redis = request.app.state.redis

    # Fetch student's needs assessment
    stmt = (
        select(NeedsAssessmentResponse)
        .where(NeedsAssessmentResponse.profile_id == student_profile_id)
        .order_by(NeedsAssessmentResponse.submitted_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    assessment = result.scalar_one_or_none()

    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NO_ASSESSMENT",
                "message": "Complete your needs assessment first at POST /assessment",
            },
        )

    # Get available peers (RULE-04)
    available_peers = await _get_available_peers(db)

    if available_peers:
        # ── Match ────────────────────────────────────────────────────────────
        peer = available_peers[0]  # lowest-load peer

        # Create chat session
        chat_session = ChatSession(
            student_profile_id=student_profile_id,
            peer_counselor_profile_id=peer.id,
            started_at=datetime.now(tz=timezone.utc),
        )
        db.add(chat_session)
        
        # Increment peer counters
        peer.sessions_completed += 1
        peer.daily_session_count += 1
        
        # Check if peer hit daily cap or burnout threshold
        if peer.daily_session_count >= DAILY_SESSION_CAP:
            peer.available = False
            logger.info(f"👤 Peer {peer.id} hit daily cap ({DAILY_SESSION_CAP} sessions)")
        
        if peer.sessions_completed >= BURNOUT_THRESHOLD:
            peer.available = False
            peer.account_status = AccountStatusEnum.unavailable
            logger.warning(f"⚠️ Peer {peer.id} reached burnout threshold ({BURNOUT_THRESHOLD} sessions)")

        await db.flush()
        
        # Remove student from queue if they were enqueued
        if redis:
            await _remove_from_queue(redis, str(student_profile_id))

        await db.commit()

        logger.info(f"✅ Matched student {student_profile_id} to peer {peer.id}")

        return {
            "status": "matched",
            "session_id": str(chat_session.id),
            "queue_position": None,
            "estimated_wait_minutes": None,
            "message": f"Matched with peer counselor! Session ID: {chat_session.id}",
        }

    else:
        # ── Enqueue ──────────────────────────────────────────────────────────
        if not redis:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "NO_PEERS_AVAILABLE",
                    "message": "No peer counselors available right now. Try again later or browse resources.",
                },
            )

        position, estimated_wait = await _enqueue_student(redis, str(student_profile_id))

        logger.info(f"📋 Enqueued student {student_profile_id} at position {position}")

        return {
            "status": "queued",
            "session_id": None,
            "queue_position": position,
            "estimated_wait_minutes": estimated_wait,
            "message": f"No peers available. You are #{position} in queue. Expected wait: ~{estimated_wait} min. Explore resources while you wait.",
        }


@router.get("/queue-status")
async def get_queue_status(
    request: Request,
    user: dict = Depends(consent_required),
) -> dict[str, Any]:
    """
    Get the current user's queue position and estimated wait time.
    
    Returns:
    {
        position: int | null,
        estimated_wait_minutes: int | null,
        message: string
    }
    
    If the user is not in the queue, returns position=null.
    """
    student_profile_id = str(user.get("sub"))
    redis: Redis = request.app.state.redis

    if not redis:
        return {"position": None, "estimated_wait_minutes": None, "message": "Queue unavailable"}

    queue_key = "matching_queue"
    rank = await redis.zrank(queue_key, student_profile_id)

    if rank is None:
        return {
            "position": None,
            "estimated_wait_minutes": None,
            "message": "Not in queue. Request a match at POST /matching/request",
        }

    position = rank + 1
    estimated_wait = max(5, position * 5)

    return {
        "position": position,
        "estimated_wait_minutes": estimated_wait,
        "message": f"You are #{position} in queue (~{estimated_wait} min wait)",
    }
