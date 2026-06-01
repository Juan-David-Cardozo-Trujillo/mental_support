"""
Peer Counselor Portal Router
=============================

Peer-specific dashboard and management endpoints:
- Dashboard with stats (sessions, ratings, badges)
- Wellness check and burnout warnings
- Availability toggle
- Session history and feedback
- Training progress

Endpoints:
  GET  /peer/dashboard          → Peer dashboard with stats
  GET  /peer/wellness           → Burnout check and recommendations
  POST /peer/availability       → Toggle availability
  GET  /peer/sessions           → Session history with feedback
  GET  /peer/badges             → Recognition badges earned
  GET  /peer/training-progress  → Training module completion status
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from backend.core.database import get_platform_db
from backend.core.security import get_current_user, consent_required, require_role
from backend.db.platform_models import (
    PeerCounselorProfile,
    ChatSession,
    ChatMessage,
    PeerReport,
    RecognitionBadge,
    Feedback,
    TrainingCompletion,
    AccountStatusEnum,
    SessionStatusEnum,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/peer", tags=["Peer Portal"])

# ──────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────────────────────────────────────

class PeerStats(BaseModel):
    """Peer performance statistics."""
    sessions_completed: int
    average_rating: Optional[float]
    total_messages_sent: int
    reports_received_7d: int
    badges_earned: int
    daily_session_count: int
    max_daily_sessions: int = 3


class BurnoutIndicator(BaseModel):
    """Burnout warning level."""
    level: str  # "green", "yellow", "red"
    sessions_completed: int
    burnout_threshold: int
    daily_sessions: int
    max_daily_sessions: int
    reports_7d: int
    report_threshold: int
    recommendation: str


class DashboardResponse(BaseModel):
    """Peer dashboard."""
    profile_id: str
    name: str
    available: bool
    account_status: str
    stats: PeerStats
    burnout_indicator: BurnoutIndicator
    training_completed: bool
    total_messages_sent: int


class SessionHistoryItem(BaseModel):
    """Session with feedback."""
    session_id: str
    student_anonymous_profile_id: str
    session_status: str
    messages_count: int
    duration_minutes: Optional[float]
    feedback_rating: Optional[int]
    feedback_text: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class BadgeInfo(BaseModel):
    """Recognition badge."""
    badge_name: str
    description: str
    awarded_at: datetime


class TrainingProgress(BaseModel):
    """Training module progress."""
    module_name: str
    status: str  # pending, in_progress, completed
    completion_date: Optional[datetime]
    score: Optional[int]


# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────────────────────

async def _calculate_burnout_indicator(
    sessions_completed: int,
    daily_sessions: int,
    reports_7d: int,
    burnout_threshold: int = 20,
    max_daily: int = 3,
    report_threshold: int = 3,
) -> BurnoutIndicator:
    """
    Calculate burnout risk level and recommendation.
    
    RULE-02: Burnout threshold at 20 sessions
    Daily cap at 3 sessions
    Report threshold at 3 in 7 days
    """
    
    # Calculate risk score
    session_risk = min(sessions_completed / burnout_threshold, 1.0)  # 0-1
    daily_risk = min(daily_sessions / max_daily, 1.0)  # 0-1
    report_risk = min(reports_7d / report_threshold, 1.0)  # 0-1
    
    avg_risk = (session_risk + daily_risk + report_risk) / 3
    
    if avg_risk < 0.5:
        level = "green"
        recommendation = "You're doing great! Keep up the good work."
    elif avg_risk < 0.8:
        level = "yellow"
        recommendation = (
            "⚠️ You're approaching your limits. Consider taking a break soon "
            "to prevent burnout. Your wellbeing matters!"
        )
    else:
        level = "red"
        recommendation = (
            "🔴 BURNOUT WARNING: Please take a break. "
            "You've reached or exceeded recommended limits. "
            "Contact your supervisor or take time off."
        )
    
    return BurnoutIndicator(
        level=level,
        sessions_completed=sessions_completed,
        burnout_threshold=burnout_threshold,
        daily_sessions=daily_sessions,
        max_daily_sessions=max_daily,
        reports_7d=reports_7d,
        report_threshold=report_threshold,
        recommendation=recommendation,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=DashboardResponse)
async def get_peer_dashboard(
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("peer_counselor")),
):
    """
    Get peer counselor dashboard with stats and burnout indicators.
    
    Peer-only endpoint.
    """
    try:
        peer_id = current_user["profile_id"]
        
        peer_result = await db.execute(
            select(PeerCounselorProfile).where(
                PeerCounselorProfile.profile_id == peer_id
            )
        )
        peer = peer_result.scalar_one_or_none()
        
        if not peer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Peer profile not found"
            )
        
        # Get average feedback rating
        rating_result = await db.execute(
            select(func.avg(Feedback.overall_satisfaction))
            .select_from(Feedback)
            .join(ChatSession)
            .where(ChatSession.peer_counselor_profile_id == peer.id)
        )
        avg_rating = rating_result.scalar()
        
        # Count total messages sent
        messages_result = await db.execute(
            select(func.count(ChatMessage.id))
            .join(ChatSession)
            .where(
                and_(
                    ChatSession.peer_counselor_profile_id == peer.id,
                    ChatMessage.sender_role == "peer_counselor"
                )
            )
        )
        total_messages = messages_result.scalar() or 0
        
        # Count badges
        badges_result = await db.execute(
            select(func.count(RecognitionBadge.id)).where(
                RecognitionBadge.peer_profile_id == peer.id
            )
        )
        badges_count = badges_result.scalar() or 0
        
        # Check training status
        training_result = await db.execute(
            select(TrainingCompletion).where(
                and_(
                    TrainingCompletion.peer_profile_id == peer.id,
                    TrainingCompletion.completed_at.isnot(None)
                )
            )
        )
        training_completed = training_result.scalar_one_or_none() is not None
        
        # Build stats
        stats = PeerStats(
            sessions_completed=peer.sessions_completed or 0,
            average_rating=float(avg_rating) if avg_rating else None,
            total_messages_sent=total_messages,
            reports_received_7d=peer.report_count_7d or 0,
            badges_earned=badges_count,
            daily_session_count=peer.daily_session_count or 0,
            max_daily_sessions=3,
        )
        
        # Calculate burnout indicator
        burnout = await _calculate_burnout_indicator(
            sessions_completed=peer.sessions_completed or 0,
            daily_sessions=peer.daily_session_count or 0,
            reports_7d=peer.report_count_7d or 0,
        )
        
        dashboard = DashboardResponse(
            profile_id=str(peer_id),
            name="Peer Counselor",  # No PII returned
            available=peer.available,
            account_status=peer.account_status or "active",
            stats=stats,
            burnout_indicator=burnout,
            training_completed=training_completed,
            total_messages_sent=total_messages,
        )
        
        logger.info(f"✓ Dashboard retrieved for peer {peer_id}")
        return dashboard
        
    except Exception as e:
        logger.error(f"✗ Error retrieving dashboard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard"
        )


@router.get("/wellness", response_model=BurnoutIndicator)
async def get_wellness_check(
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("peer_counselor")),
):
    """
    Get detailed wellness check and burnout indicators.
    
    RULE-02: Checks against:
    - 20 session burnout threshold
    - 3 sessions/day limit
    - 3 reports in 7 days suspension threshold
    """
    try:
        peer_id = current_user["profile_id"]
        
        peer_result = await db.execute(
            select(PeerCounselorProfile).where(
                PeerCounselorProfile.profile_id == peer_id
            )
        )
        peer = peer_result.scalar_one_or_none()
        
        if not peer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Peer profile not found"
            )
        
        burnout = await _calculate_burnout_indicator(
            sessions_completed=peer.sessions_completed or 0,
            daily_sessions=peer.daily_session_count or 0,
            reports_7d=peer.report_count_7d or 0,
        )
        
        logger.debug(f"✓ Wellness check: {burnout.level} for peer {peer_id}")
        return burnout
        
    except Exception as e:
        logger.error(f"✗ Error checking wellness: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check wellness status"
        )


@router.post("/availability", response_model=dict)
async def toggle_availability(
    available: bool,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("peer_counselor")),
):
    """
    Toggle peer availability for matching.
    
    When set to false:
    - Peer won't be matched with new students
    - Won't appear in availability slots
    - Can still view/manage existing sessions
    """
    try:
        peer_id = current_user["profile_id"]
        
        peer_result = await db.execute(
            select(PeerCounselorProfile).where(
                PeerCounselorProfile.profile_id == peer_id
            )
        )
        peer = peer_result.scalar_one_or_none()
        
        if not peer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Peer profile not found"
            )
        
        peer.available = available
        await db.commit()
        
        status_text = "available" if available else "unavailable"
        logger.info(f"✓ Peer {peer_id} set to {status_text}")
        
        return {
            "available": available,
            "message": f"You are now {status_text} for matching"
        }
        
    except Exception as e:
        await db.rollback()
        logger.error(f"✗ Error updating availability: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update availability"
        )


@router.get("/sessions", response_model=list[SessionHistoryItem])
async def get_session_history(
    status_filter: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("peer_counselor")),
):
    """
    Get session history with feedback.
    
    Query Parameters:
    - status_filter: Filter by status (active, closed, flagged)
    - limit: Max results (default 50)
    """
    try:
        peer_result = await db.execute(
            select(PeerCounselorProfile).where(PeerCounselorProfile.profile_id == peer_id)
        )
        peer = peer_result.scalar_one_or_none()
        if not peer:
            raise HTTPException(status_code=404, detail="Peer profile not found")

        query = select(ChatSession).where(
            ChatSession.peer_counselor_profile_id == peer.id
        )
        
        if status_filter:
            query = query.where(ChatSession.session_status == status_filter)
        
        query = query.order_by(ChatSession.started_at.desc()).limit(limit)
        
        result = await db.execute(query)
        sessions = result.scalars().all()
        
        history = []
        for session in sessions:
            # Count messages
            msg_result = await db.execute(
                select(func.count(ChatMessage.id)).where(
                    ChatMessage.session_id == session.id
                )
            )
            msg_count = msg_result.scalar() or 0
            
            # Get feedback if exists
            feedback_result = await db.execute(
                select(Feedback).where(
                    Feedback.session_id == session.id
                )
            )
            feedback = feedback_result.scalar_one_or_none()
            
            duration = None
            if session.ended_at:
                duration = (session.ended_at - session.started_at).total_seconds() / 60
            
            history.append(
                SessionHistoryItem(
                    session_id=str(session.id),
                    student_anonymous_profile_id=str(session.student_profile_id),
                    session_status=session.session_status,
                    messages_count=msg_count,
                    duration_minutes=duration,
                    feedback_rating=feedback.overall_satisfaction if feedback else None,
                    feedback_text=None,
                    started_at=session.started_at,
                    ended_at=session.ended_at,
                )
            )
        
        logger.info(f"✓ Retrieved {len(history)} sessions for peer {peer_id}")
        return history
        
    except Exception as e:
        logger.error(f"✗ Error retrieving session history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session history"
        )


@router.get("/badges", response_model=list[BadgeInfo])
async def get_badges(
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("peer_counselor")),
):
    """Get all recognition badges earned."""
    try:
        peer_result = await db.execute(
            select(PeerCounselorProfile).where(PeerCounselorProfile.profile_id == peer_id)
        )
        peer = peer_result.scalar_one_or_none()
        if not peer: return []
        
        result = await db.execute(
            select(RecognitionBadge).where(
                RecognitionBadge.peer_profile_id == peer.id
            ).order_by(
                RecognitionBadge.awarded_at.desc()
            )
        )
        
        badges = result.scalars().all()
        
        return [
            BadgeInfo(
                badge_name=b.badge_name,
                description=b.description,
                awarded_at=b.awarded_at,
            )
            for b in badges
        ]
        
    except Exception as e:
        logger.error(f"✗ Error retrieving badges: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve badges"
        )


@router.get("/training-progress", response_model=list[TrainingProgress])
async def get_training_progress(
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("peer_counselor")),
):
    """Get training module completion status."""
    try:
        peer_result = await db.execute(
            select(PeerCounselorProfile).where(PeerCounselorProfile.profile_id == peer_id)
        )
        peer = peer_result.scalar_one_or_none()
        if not peer: return []
        
        result = await db.execute(
            select(TrainingCompletion).where(
                TrainingCompletion.peer_profile_id == peer.id
            )
        )
        
        completions = result.scalars().all()
        
        return [
            TrainingProgress(
                module_name=str(c.module_id),
                status="completed" if c.completed_at else "in_progress",
                completion_date=c.completed_at,
                score=c.score,
            )
            for c in completions
        ]
        
    except Exception as e:
        logger.error(f"✗ Error retrieving training progress: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve training progress"
        )
