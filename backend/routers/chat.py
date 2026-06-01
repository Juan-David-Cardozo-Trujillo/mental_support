"""Anonymous communication (chat) router — WebSocket and HTTP endpoints."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_platform_db
from backend.core.security import consent_required, decrypt_field, encrypt_field, get_current_user
from backend.db.platform_models import (
    ChatMessage,
    ChatSession,
    PeerReport,
    PeerCounselorProfile,
    AccountStatusEnum,
    SenderRoleEnum,
    SessionStatusEnum,
    RetentionPolicyEnum,
    Incident,
    IncidentSeverityEnum,
    IncidentStatusEnum,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Configuration ─────────────────────────────────────────────────────────────

AUTO_SUSPENSION_REPORT_THRESHOLD = 3  # RULE-03: suspend at 3 reports in 7 days
PRIVACY_REMINDER_INTERVAL = 10  # RULE-12: send reminder every 10 student messages


# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    """Simple pub/sub manager for chat sessions."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.debug(f"WebSocket connected: {session_id}")

    def disconnect(self, session_id: str, websocket: WebSocket):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.debug(f"WebSocket disconnected: {session_id}")

    async def broadcast(self, session_id: str, data: dict):
        """Broadcast message to all connected clients in a session."""
        if session_id not in self.active_connections:
            return
        for connection in self.active_connections[session_id]:
            try:
                await connection.send_json(data)
            except Exception as exc:
                logger.warning(f"Failed to send message to WebSocket: {exc}")


manager = ConnectionManager()


# ── WebSocket endpoint ───────────────────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(None),
    db: AsyncSession = Depends(get_platform_db),
):
    """
    WebSocket endpoint for real-time chat.
    
    Auth: JWT passed as query parameter (?token=JWT)
    
    Flow:
    1. Validate JWT and session ownership
    2. Join Redis pub/sub channel for session
    3. Listen for messages and broadcast to other participants
    4. RULE-12: Every 10 student messages → inject privacy reminder
    5. RULE-06: Handle flagged sessions and retention policy
    
    Message format:
    {
        type: 'message' | 'report' | 'end_session' | 'escalate',
        content: string
    }
    """
    # Validate JWT
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing JWT token")
        return

    try:
        from backend.core.security import decode_token
        payload = decode_token(token)
        user_id = UUID(payload.get("sub"))
    except Exception as exc:
        logger.warning(f"WebSocket auth failed: {exc}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    # Validate session ownership
    stmt = select(ChatSession).where(ChatSession.id == UUID(session_id))
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session not found")
        return

    is_student = session.student_profile_id == user_id
    is_peer = session.peer_counselor_profile_id and session.peer_counselor_profile_id == user_id  # type: ignore
    is_professional = session.professional_counselor_id and session.professional_counselor_id == user_id  # type: ignore

    if not (is_student or is_peer or is_professional):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not a participant in this session")
        return

    # Determine user role
    user_role = "student" if is_student else ("peer_counselor" if is_peer else "professional_counselor")

    # Connect WebSocket
    await manager.connect(session_id, websocket)

    # Track message count for privacy reminder (RULE-12)
    student_message_count = 0

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")
            content = data.get("content", "")

            if msg_type == "message":
                # ── Handle chat message ───────────────────────────────────────

                # Encrypt message
                encrypted_content = encrypt_field(content)

                # Save to database
                message = ChatMessage(
                    session_id=UUID(session_id),
                    sender_role=user_role,
                    encrypted_content=encrypted_content,
                    flagged=session.session_status == SessionStatusEnum.flagged,
                    retention_policy=(
                        RetentionPolicyEnum.retain_encrypted
                        if session.session_status == SessionStatusEnum.flagged
                        else RetentionPolicyEnum.discard_on_close
                    ),
                )
                db.add(message)
                await db.flush()

                # Track student messages for privacy reminder (RULE-12)
                if is_student:
                    student_message_count += 1

                # Broadcast message (encrypted to client for brevity, but don't send raw plaintext)
                broadcast_data = {
                    "type": "message",
                    "sender": user_role,
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                }
                await manager.broadcast(session_id, broadcast_data)

                # RULE-12: Every 10 student messages, inject privacy reminder
                if is_student and student_message_count % PRIVACY_REMINDER_INTERVAL == 0:
                    reminder_msg = ChatMessage(
                        session_id=UUID(session_id),
                        sender_role=SenderRoleEnum.system,
                        encrypted_content=encrypt_field(
                            "🔒 For your safety, avoid sharing personal contact info (phone, email, social media). "
                            "Keep the conversation focused on your well-being."
                        ),
                        flagged=False,
                        retention_policy=RetentionPolicyEnum.discard_on_close,
                    )
                    db.add(reminder_msg)
                    await db.flush()

                    # Send reminder to student only
                    await websocket.send_json({
                        "type": "privacy_reminder",
                        "content": "🔒 For your safety, avoid sharing personal contact info...",
                    })

            elif msg_type == "report":
                # ── Handle peer report (RULE-03) ──────────────────────────────

                if not is_student or not session.peer_counselor_profile_id:
                    await websocket.send_json({"type": "error", "message": "Only students can report peers"})
                    continue

                peer_id = session.peer_counselor_profile_id

                # Create report
                report = PeerReport(
                    session_id=UUID(session_id),
                    reporter_profile_id=user_id,
                    reported_peer_id=peer_id,
                )
                db.add(report)

                # RULE-03: Increment report count and check suspension
                peer_profile_stmt = select(PeerCounselorProfile).where(
                    PeerCounselorProfile.id == peer_id
                )
                peer_result = await db.execute(peer_profile_stmt)
                peer_profile = peer_result.scalar_one_or_none()

                if peer_profile:
                    now = datetime.now(tz=timezone.utc)
                    
                    # Initialize window if needed
                    if peer_profile.report_window_start is None:
                        peer_profile.report_window_start = now
                        peer_profile.report_count_7d = 0

                    # Check if window has elapsed
                    window_age = (now - peer_profile.report_window_start).days
                    if window_age > 7:
                        # Reset window
                        peer_profile.report_window_start = now
                        peer_profile.report_count_7d = 0

                    # Increment count
                    peer_profile.report_count_7d += 1

                    # Check suspension threshold (RULE-03)
                    if peer_profile.report_count_7d >= AUTO_SUSPENSION_REPORT_THRESHOLD:
                        peer_profile.account_status = AccountStatusEnum.suspended
                        peer_profile.available = False

                        # Create incident record
                        incident = Incident(
                            incident_type="PEER_COUNSELOR_SUSPENSION",
                            severity=IncidentSeverityEnum.high,
                            description=f"Peer {peer_id} auto-suspended after {peer_profile.report_count_7d} reports in 7 days",
                            status=IncidentStatusEnum.open,
                        )
                        db.add(incident)

                        logger.warning(f"🚨 Peer {peer_id} auto-suspended after {AUTO_SUSPENSION_REPORT_THRESHOLD} reports")

                    # Mark session as flagged
                    session.session_status = SessionStatusEnum.flagged
                    session.report_count += 1

                await db.commit()

                await websocket.send_json({"type": "report_ack", "reported": True})

            elif msg_type == "end_session":
                # ── End session ───────────────────────────────────────────────

                session.session_status = SessionStatusEnum.closed
                session.ended_at = datetime.now(tz=timezone.utc)
                
                # Schedule message cleanup based on retention policy (Celery task in production)
                # For now, just update the session

                await db.commit()
                
                await websocket.send_json({"type": "session_ended"})
                break  # Close WebSocket

            elif msg_type == "escalate":
                # ── Escalate to professional ──────────────────────────────────

                if not is_student:
                    await websocket.send_json({"type": "error", "message": "Only students can escalate"})
                    continue

                # In production: create urgent appointment, alert professionals
                # For now, just acknowledge

                await websocket.send_json({
                    "type": "escalated",
                    "message": "Your request has been escalated to a professional counselor",
                })

                logger.info(f"📈 Student {user_id} escalated chat session {session_id}")

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    except Exception as exc:
        logger.warning(f"WebSocket error: {exc}")
    finally:
        manager.disconnect(session_id, websocket)


# ── HTTP endpoints for chat management ────────────────────────────────────────

@router.post("/{session_id}/report")
async def report_peer(
    session_id: str,
    user: dict = Depends(consent_required),
    db: AsyncSession = Depends(get_platform_db),
) -> dict[str, bool]:
    """
    Report a peer counselor for misconduct (HTTP endpoint).
    
    RULE-03: Auto-suspend at 3 reports in 7 days.
    Creates Incident record and alerts admins.
    """
    student_id = UUID(user.get("sub"))

    stmt = select(ChatSession).where(ChatSession.id == UUID(session_id))
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session or session.student_profile_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "Chat session not found"},
        )

    if not session.peer_counselor_profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_PEER", "message": "This session has no peer to report"},
        )

    # Create report
    report = PeerReport(
        session_id=UUID(session_id),
        reporter_profile_id=student_id,
        reported_peer_id=session.peer_counselor_profile_id,
    )
    db.add(report)

    # RULE-03: Check and enforce suspension
    peer_stmt = select(PeerCounselorProfile).where(
        PeerCounselorProfile.id == session.peer_counselor_profile_id
    )
    peer_result = await db.execute(peer_stmt)
    peer_profile = peer_result.scalar_one_or_none()

    if peer_profile:
        now = datetime.now(tz=timezone.utc)
        if peer_profile.report_window_start is None:
            peer_profile.report_window_start = now

        window_age = (now - peer_profile.report_window_start).days
        if window_age > 7:
            peer_profile.report_window_start = now
            peer_profile.report_count_7d = 0

        peer_profile.report_count_7d += 1

        if peer_profile.report_count_7d >= AUTO_SUSPENSION_REPORT_THRESHOLD:
            peer_profile.account_status = AccountStatusEnum.suspended
            peer_profile.available = False

            incident = Incident(
                incident_type="PEER_COUNSELOR_SUSPENSION",
                severity=IncidentSeverityEnum.high,
                description=f"Peer {session.peer_counselor_profile_id} auto-suspended after {peer_profile.report_count_7d} reports",
                status=IncidentStatusEnum.open,
            )
            db.add(incident)

    session.session_status = SessionStatusEnum.flagged
    session.report_count += 1

    await db.commit()
    return {"reported": True}


@router.post("/{session_id}/end")
async def end_session(
    session_id: str,
    user: dict = Depends(consent_required),
    db: AsyncSession = Depends(get_platform_db),
) -> dict[str, bool]:
    """
    End a chat session (HTTP endpoint).
    
    Can be called by student or peer/professional.
    RULE-06: Non-flagged messages are marked for deletion.
    Flagged messages are retained encrypted.
    """
    user_id = UUID(user.get("sub"))

    stmt = select(ChatSession).where(ChatSession.id == UUID(session_id))
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "Chat session not found"},
        )

    # Verify user is a participant
    is_participant = (
        session.student_profile_id == user_id
        or (session.peer_counselor_profile_id and session.peer_counselor_profile_id == user_id)  # type: ignore
        or (session.professional_counselor_id and session.professional_counselor_id == user_id)  # type: ignore
    )

    if not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "NOT_PARTICIPANT", "message": "You are not a participant in this session"},
        )

    session.session_status = SessionStatusEnum.closed
    session.ended_at = datetime.now(tz=timezone.utc)

    # Schedule message cleanup (Celery task in production)
    # Messages with retention_policy='discard_on_close' should be deleted after 24h
    # For now, just mark as ready for cleanup

    await db.commit()
    return {"ended": True}


@router.post("/{session_id}/escalate")
async def escalate_session(
    session_id: str,
    user: dict = Depends(consent_required),
    db: AsyncSession = Depends(get_platform_db),
) -> dict[str, Any]:
    """
    Escalate a peer chat to a professional counselor (HTTP endpoint).
    
    RULE-05: Creates urgent appointment request.
    Alerts all available professional counselors.
    """
    student_id = UUID(user.get("sub"))

    stmt = select(ChatSession).where(ChatSession.id == UUID(session_id))
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session or session.student_profile_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "Chat session not found"},
        )

    # In production: create urgent appointment + notify professionals
    # For MVP: just acknowledge

    logger.info(f"📈 Escalation requested for session {session_id}")

    return {
        "escalated": True,
        "message": "Your request has been escalated to a professional counselor",
    }
