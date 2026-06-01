"""
Security utilities for the Mental Health Platform.

Provides:
- JWT creation/decoding
- AES-256-GCM field-level encryption/decryption
- SHA-256 hashing
- FastAPI dependency: get_current_user (reads JWT from HttpOnly cookie)
- FastAPI dependency factories: require_role, consent_required, training_gate
- Rate-limiting middleware (Redis-backed, sliding window)
- Session inactivity middleware (Redis last_activity tracking, 30 min timeout)
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.core.config import settings
from backend.core.database import get_platform_db
from backend.db.platform_models import AnonymousProfile, ConsentRecord

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_aes_key() -> bytes:
    """Derive the 32-byte AES key from the hex-encoded config value."""
    return bytes.fromhex(settings.AES_KEY)


# ── Hashing ───────────────────────────────────────────────────────────────────

def hash_value(value: str) -> str:
    """Return the SHA-256 hex digest of *value*. Used for SSO tokens and IPs."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ── AES-256-GCM field-level encryption ───────────────────────────────────────

def encrypt_field(plaintext: str) -> bytes:
    """
    Encrypt *plaintext* with AES-256-GCM.

    Returns:  nonce (12 bytes) || ciphertext+tag
    The nonce is randomly generated per call, so encrypting the same value
    twice yields different ciphertext — perfect forward secrecy at the field level.
    """
    key = _get_aes_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext  # prepend nonce for storage


def decrypt_field(ciphertext_with_nonce: bytes) -> str:
    """
    Decrypt a value produced by :func:`encrypt_field`.

    Expects: nonce (12 bytes) || ciphertext+tag
    """
    key = _get_aes_key()
    aesgcm = AESGCM(key)
    nonce = ciphertext_with_nonce[:12]
    ciphertext = ciphertext_with_nonce[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(data: dict[str, Any]) -> str:
    """
    Create a signed JWT containing *data* and an expiry claim.

    The token carries only non-PII fields (profile_id, role, account_status).
    """
    payload = data.copy()
    expire = datetime.now(tz=timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload.update({"exp": expire, "iat": datetime.now(tz=timezone.utc)})
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT, raising HTTP 401 on any failure.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── Current-user dependency ───────────────────────────────────────────────────

async def get_current_user(
    request: Request,
    access_token: str | None = Cookie(default=None),
) -> dict[str, Any]:
    """
    FastAPI dependency: extract and validate JWT from the HttpOnly cookie.

    Also refreshes the Redis last_activity key to keep the session alive.
    Returns the decoded payload dict.
    """
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Missing access token"},
        )
    payload = decode_token(access_token)

    # Refresh session activity in Redis
    redis: aioredis.Redis = request.app.state.redis
    user_id = payload.get("sub")
    if user_id and redis:
        await redis.setex(
            f"session:activity:{user_id}",
            settings.SESSION_INACTIVITY_SECONDS,
            datetime.now(tz=timezone.utc).isoformat(),
        )
    return payload


CurrentUser = Depends(get_current_user)


# ── Role enforcement ──────────────────────────────────────────────────────────

def require_role(*roles: str):
    """
    Dependency factory: require the authenticated user to have one of *roles*.

    Usage::

        @router.get("/admin/only")
        async def admin_endpoint(user=Depends(require_role("admin"))):
            ...
    """
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": f"Role '{user.get('role')}' is not authorised for this resource",
                },
            )
        return user

    return _check


# ── Consent gate (RULE-11) ────────────────────────────────────────────────────

async def consent_required(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_platform_db),
) -> dict:
    """
    RULE-11: Every endpoint except /auth/* must confirm a ConsentRecord exists.

    If the authenticated user has no ConsentRecord → 403 CONSENT_REQUIRED.
    """
    profile_id = user.get("sub")
    result = await db.execute(
        select(ConsentRecord).where(ConsentRecord.profile_id == profile_id).limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CONSENT_REQUIRED", "message": "You must accept the consent agreement first"},
        )
    return user


# ── Peer training gate (RULE-08) ─────────────────────────────────────────────

async def training_gate(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_platform_db),
) -> dict:
    """
    RULE-08: Peer counselors with account_status='pending' can ONLY access
    /auth/*, /training/*, and /auth/me.  All other routes return 403.

    This dependency is applied to all platform routes that peers may access.
    """
    if user.get("role") != "peer_counselor":
        return user  # non-peers are unaffected by this gate

    from backend.db.platform_models import PeerCounselorProfile
    result = await db.execute(
        select(PeerCounselorProfile).where(
            PeerCounselorProfile.profile_id == user.get("sub")
        )
    )
    peer = result.scalar_one_or_none()
    if peer and peer.account_status == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TRAINING_REQUIRED",
                "message": "Complete your training before accessing this resource",
            },
        )
    return user


# ── Rate-limiting middleware ───────────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter backed by Redis.

    Keys are by IP address (or profile_id from JWT if available).
    Limit: RATE_LIMIT_REQUESTS requests per RATE_LIMIT_WINDOW_SECONDS.
    Returns HTTP 429 when exceeded.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        redis: aioredis.Redis | None = getattr(request.app.state, "redis", None)
        if redis is None:
            return await call_next(request)

        # Try to identify by profile_id from cookie, fall back to IP
        identifier = request.client.host if request.client else "unknown"
        access_token = request.cookies.get("access_token")
        if access_token:
            try:
                payload = decode_token(access_token)
                identifier = f"user:{payload.get('sub', identifier)}"
            except HTTPException:
                pass

        key = f"rate_limit:{identifier}"
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        limit = settings.RATE_LIMIT_REQUESTS

        # Atomic increment with expiry
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        results = await pipe.execute()
        count = results[0]

        if count > limit:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Too many requests. Limit: {limit}/{window}s",
                    }
                },
            )
        return await call_next(request)


# ── Session inactivity middleware ─────────────────────────────────────────────

class SessionInactivityMiddleware(BaseHTTPMiddleware):
    """
    Enforces a 30-minute inactivity timeout for authenticated users.

    On every authenticated request, checks Redis for the last_activity key.
    If the key has expired (TTL = SESSION_INACTIVITY_SECONDS), returns 401.
    The key is refreshed by :func:`get_current_user` on every request, so
    active users are never timed out mid-session.
    """

    # Paths that are exempt from inactivity check
    _EXEMPT_PREFIXES = ("/auth/", "/health", "/resources/share/")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Exempt certain paths
        for prefix in self._EXEMPT_PREFIXES:
            if request.url.path.startswith(prefix):
                return await call_next(request)

        redis: aioredis.Redis | None = getattr(request.app.state, "redis", None)
        access_token = request.cookies.get("access_token")

        if redis and access_token:
            try:
                payload = decode_token(access_token)
                user_id = payload.get("sub")
                if user_id:
                    activity_key = f"session:activity:{user_id}"
                    exists = await redis.exists(activity_key)
                    if not exists:
                        return JSONResponse(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            content={
                                "error": {
                                    "code": "SESSION_EXPIRED",
                                    "message": "Your session has expired due to inactivity",
                                }
                            },
                        )
            except HTTPException:
                pass  # let the route handler return the appropriate error

        return await call_next(request)
