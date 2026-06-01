"""Authentication router — OAuth 2.0/OIDC SSO integration."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_auth_db, get_platform_db
from backend.core.security import (
    consent_required,
    create_access_token,
    decrypt_field,
    encrypt_field,
    get_current_user,
    hash_value,
)
from backend.db.auth_models import AuthToken
from backend.db.platform_models import (
    AnonymousProfile,
    ConsentRecord,
    PeerCounselorProfile,
    RoleEnum,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Models ────────────────────────────────────────────────────────────────────

class AuthResponse(dict):
    """Response from /auth/sso/callback or /auth/login."""
    token: str
    needs_consent: bool
    needs_assessment: bool
    needs_training: bool


class CurrentUserResponse(dict):
    """Response from /auth/me."""
    profile_id: UUID
    role: str
    account_status: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/sso/start")
async def sso_start(request: Request) -> RedirectResponse:
    """
    Initiate SSO flow: redirect to university OAuth authorization endpoint.

    This endpoint:
    1. Generates a random state parameter (CSRF protection)
    2. Stores the state in Redis for 10 minutes
    3. Redirects to the university's OAuth /authorize endpoint
    """
    # Generate state and store in Redis
    state = secrets.token_urlsafe(32)
    redis = request.app.state.redis
    await redis.setex(f"oauth_state:{state}", 600, datetime.now(tz=timezone.utc).isoformat())

    # Redirect to university OAuth
    auth_url = (
        f"{settings.SSO_AUTHORIZATION_URL}"
        f"?client_id={settings.SSO_CLIENT_ID}"
        f"&redirect_uri={settings.SSO_CALLBACK_URL}"
        f"&response_type=code"
        f"&scope=openid profile email"
        f"&state={state}"
    )
    return RedirectResponse(url=auth_url)


@router.post("/sso/callback")
async def sso_callback(
    request: Request,
    code: str,
    state: str,
    auth_db: AsyncSession = Depends(get_auth_db),
    platform_db: AsyncSession = Depends(get_platform_db),
) -> dict[str, Any]:
    """
    OAuth2 callback endpoint.

    Flow:
    1. Verify state parameter (CSRF check)
    2. Exchange code for SSO token from university
    3. Extract role from token claims
    4. Hash token and store in auth_service.auth_tokens (upsert)
    5. Create or retrieve AnonymousProfile in platform_db
    6. Check if consent/assessment/training are needed
    7. Issue JWT to frontend
    
    RULE-01: No PII is returned or stored in JWT. The JWT contains only
    profile_id, role, and account_status (for peers).
    
    Returns:
    {
        token: JWT,
        needs_consent: bool,
        needs_assessment: bool,
        needs_training: bool (for peers only)
    }
    """
    # Verify state
    redis = request.app.state.redis
    stored_state = await redis.get(f"oauth_state:{state}")
    if not stored_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_STATE", "message": "State mismatch (CSRF validation failed)"},
        )
    await redis.delete(f"oauth_state:{state}")

    # Exchange code for token
    try:
        async with AsyncClient() as client:
            token_response = await client.post(
                settings.SSO_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.SSO_CLIENT_ID,
                    "client_secret": settings.SSO_CLIENT_SECRET,
                    "redirect_uri": settings.SSO_CALLBACK_URL,
                },
            )
            token_response.raise_for_status()
            token_data = token_response.json()
    except Exception as exc:
        logger.error(f"SSO token exchange failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SSO_ERROR", "message": "Failed to exchange code for token"},
        ) from exc

    # Extract identity claims from token
    access_token = token_data.get("access_token")
    sso_user_id = token_data.get("sub") or token_data.get("user_id")  # varies by provider
    sso_role = token_data.get("role", "student")  # default role if not provided

    # Hash token for storage (RULE-01: never store raw token)
    token_hash = hash_value(access_token)

    # ── Update auth_service ──────────────────────────────────────────────────

    # Upsert auth token
    stmt = select(AuthToken).where(AuthToken.token_hash == token_hash)
    existing_token = await auth_db.execute(stmt)
    token_record = existing_token.scalar_one_or_none()

    if token_record:
        token_record.last_seen = datetime.now(tz=timezone.utc)
    else:
        token_record = AuthToken(
            token_hash=token_hash,
            role=sso_role,
            created_at=datetime.now(tz=timezone.utc),
        )
        auth_db.add(token_record)

    await auth_db.commit()

    # ── Update platform_db ───────────────────────────────────────────────────

    # Create or retrieve anonymous profile
    stmt = select(AnonymousProfile).where(AnonymousProfile.auth_token_hash == token_hash)
    anon_profile = await platform_db.execute(stmt)
    profile = anon_profile.scalar_one_or_none()

    if profile is None:
        profile = AnonymousProfile(
            auth_token_hash=token_hash,
            role=sso_role,
            created_at=datetime.now(tz=timezone.utc),
        )
        platform_db.add(profile)
    else:
        profile.role = sso_role  # sync role from SSO

    await platform_db.flush()  # get profile.id

    # Check what gates are needed
    needs_consent = True
    needs_assessment = False
    needs_training = False

    # Check consent
    consent_stmt = select(ConsentRecord).where(
        ConsentRecord.profile_id == profile.id
    )
    existing_consent = await platform_db.execute(consent_stmt)
    if existing_consent.scalar_one_or_none():
        needs_consent = False

    # For peers: check training status
    if profile.role == "peer_counselor":
        peer_stmt = select(PeerCounselorProfile).where(
            PeerCounselorProfile.profile_id == profile.id
        )
        peer_profile_result = await platform_db.execute(peer_stmt)
        peer_profile = peer_profile_result.scalar_one_or_none()

        if peer_profile is None:
            # Create peer profile in pending state
            peer_profile = PeerCounselorProfile(
                profile_id=profile.id,
                account_status="pending",
            )
            platform_db.add(peer_profile)
            needs_training = True
        else:
            needs_training = not peer_profile.training_completed

        await platform_db.flush()

    # For students: check assessment status
    if profile.role == "student":
        # Check if needs_assessment response exists
        from backend.db.platform_models import NeedsAssessmentResponse
        assessment_stmt = select(NeedsAssessmentResponse).where(
            NeedsAssessmentResponse.profile_id == profile.id
        )
        existing_assessment = await platform_db.execute(assessment_stmt)
        if existing_assessment.scalar_one_or_none() is None:
            needs_assessment = True

    await platform_db.commit()

    # ── Issue JWT ────────────────────────────────────────────────────────────

    jwt_data = {
        "sub": str(profile.id),
        "role": profile.role,
    }
    if profile.role == "peer_counselor" and peer_profile:
        jwt_data["account_status"] = peer_profile.account_status

    access_token_jwt = create_access_token(jwt_data)

    # Set HttpOnly cookie
    response_dict = {
        "token": access_token_jwt,
        "needs_consent": needs_consent,
        "needs_assessment": needs_assessment,
        "needs_training": needs_training,
    }

    # Return response with Set-Cookie header
    from fastapi.responses import JSONResponse
    response = JSONResponse(content=response_dict)
    response.set_cookie(
        key="access_token",
        value=access_token_jwt,
        httponly=True,
        secure=not settings.DEBUG,  # HTTPS only in production
        samesite="strict",
        max_age=settings.JWT_EXPIRE_HOURS * 3600,
    )
    return response


@router.post("/consent")
async def consent(
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_platform_db),
) -> dict[str, Any]:
    """
    Accept the privacy policy and terms of use.
    
    RULE-11: After this endpoint succeeds, the user can access protected endpoints.
    
    Body: {consent_version: string}
    Returns: {consented: true}
    """
    body = await request.json()
    consent_version = body.get("consent_version", "1.0.0")

    profile_id = user.get("sub")
    ip_hash = hash_value(request.client.host) if request.client else None

    record = ConsentRecord(
        profile_id=profile_id,
        consent_version=consent_version,
        ip_hash=ip_hash,
        accepted_at=datetime.now(tz=timezone.utc),
    )
    db.add(record)
    await db.commit()

    return {"consented": True}


@router.get("/me")
async def get_current_user_info(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_platform_db),
) -> CurrentUserResponse:
    """
    Get the current authenticated user's profile information.
    
    RULE-01: Returns only non-PII fields (profile_id, role, account_status).
    Does NOT return any SSO identity, email, or name.
    
    Returns:
    {
        profile_id: UUID,
        role: string,
        account_status: string (peer only)
    }
    """
    profile_id = user.get("sub")
    role = user.get("role")

    response: dict[str, Any] = {
        "profile_id": profile_id,
        "role": role,
    }

    # Fetch peer account status if applicable
    if role == "peer_counselor":
        stmt = select(PeerCounselorProfile).where(
            PeerCounselorProfile.profile_id == profile_id
        )
        result = await db.execute(stmt)
        peer_profile = result.scalar_one_or_none()
        if peer_profile:
            response["account_status"] = peer_profile.account_status

    return response  # type: ignore


@router.post("/logout")
async def logout(response: Response) -> dict[str, Any]:
    """
    Logout endpoint: clear HttpOnly cookie.
    """
    response.delete_cookie("access_token")
    return {"logged_out": True}
