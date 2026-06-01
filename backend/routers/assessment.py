"""Needs assessment router."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_platform_db
from backend.core.security import consent_required, get_current_user, training_gate
from backend.db.platform_models import (
    NeedsAssessmentResponse,
    SupportTypeEnum,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assessment", tags=["Assessment"])


# ── Models ────────────────────────────────────────────────────────────────────

class AssessmentRequest(dict):
    """Request body for POST /assessment."""
    stress_level: int  # 1-5
    support_type_preference: str  # 'peer' | 'professional' | 'resources' | 'all'
    anonymous_preference: bool
    urgency_flag: bool


class AssessmentResponse(dict):
    """Response from POST /assessment."""
    response_id: str
    recommendation: str  # 'peer_chat' | 'appointment' | 'resources' | 'urgent'


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("")
async def submit_assessment(
    request: Request,
    user: dict = Depends(consent_required),  # implies authenticated + consented
    db: AsyncSession = Depends(get_platform_db),
) -> AssessmentResponse:
    """
    Submit needs assessment form.
    
    This endpoint:
    1. Validates input (stress_level 1-5, support_type in allowed values)
    2. Creates NeedsAssessmentResponse record
    3. RULE-05: If urgency_flag=true → skip peer matching, create urgent appointment
    4. Returns routing recommendation to frontend
    
    Body:
    {
        stress_level: int(1-5),
        support_type_preference: string ('peer' | 'professional' | 'resources' | 'all'),
        anonymous_preference: bool,
        urgency_flag: bool
    }
    
    Returns:
    {
        response_id: UUID,
        recommendation: 'peer_chat' | 'appointment' | 'resources' | 'urgent'
    }
    """
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_JSON", "message": "Request body is not valid JSON"},
        ) from exc

    # Extract and validate fields
    stress_level = body.get("stress_level")
    support_type = body.get("support_type_preference")
    anonymous_pref = body.get("anonymous_preference", True)
    urgency_flag = body.get("urgency_flag", False)

    # Validate stress_level
    if not isinstance(stress_level, int) or stress_level < 1 or stress_level > 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_STRESS_LEVEL",
                "message": "stress_level must be an integer between 1 and 5",
            },
        )

    # Validate support_type
    valid_types = ["peer", "professional", "resources", "all"]
    if support_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_SUPPORT_TYPE",
                "message": f"support_type_preference must be one of {valid_types}",
            },
        )

    profile_id = user.get("sub")

    # Create assessment response
    assessment = NeedsAssessmentResponse(
        profile_id=profile_id,
        stress_level=stress_level,
        support_type_preference=support_type,
        anonymous_preference=anonymous_pref,
        urgency_flag=urgency_flag,
        submitted_at=datetime.now(tz=timezone.utc),
    )
    db.add(assessment)
    await db.flush()  # get assessment.id

    # Determine routing recommendation
    recommendation = "resources"  # default fallback

    if urgency_flag:
        # RULE-05: Urgent escalation
        # In production, this triggers immediate appointment request + alerts
        recommendation = "urgent"
        logger.warning(f"🚨 URGENT assessment from {profile_id}: {stress_level}/5 stress")
    elif anonymous_pref and support_type in ["peer", "all"]:
        # Route to peer matching
        recommendation = "peer_chat"
    elif support_type in ["professional", "all"]:
        # Route to appointment booking
        recommendation = "appointment"
    else:
        # Route to resource library
        recommendation = "resources"

    await db.commit()

    return {
        "response_id": str(assessment.id),
        "recommendation": recommendation,
    }


@router.get("")
async def get_assessment(
    user: dict = Depends(consent_required),
    db: AsyncSession = Depends(get_platform_db),
) -> dict[str, Any]:
    """
    Retrieve the user's latest assessment response (if any).
    
    Returns the most recent NeedsAssessmentResponse for the authenticated user.
    If no assessment exists, returns null.
    """
    profile_id = user.get("sub")

    stmt = (
        select(NeedsAssessmentResponse)
        .where(NeedsAssessmentResponse.profile_id == profile_id)
        .order_by(NeedsAssessmentResponse.submitted_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    assessment = result.scalar_one_or_none()

    if not assessment:
        return {
            "response": None,
            "message": "No assessment found; create one at POST /assessment",
        }

    return {
        "response": {
            "response_id": str(assessment.id),
            "stress_level": assessment.stress_level,
            "support_type_preference": assessment.support_type_preference,
            "anonymous_preference": assessment.anonymous_preference,
            "urgency_flag": assessment.urgency_flag,
            "submitted_at": assessment.submitted_at.isoformat(),
        }
    }
