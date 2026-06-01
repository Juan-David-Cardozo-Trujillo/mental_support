"""
Database configuration — ZERO-KNOWLEDGE architecture (RULE-01).

Two completely separate async SQLAlchemy engines:
  - auth_engine  → auth_service DB  (AuthSession)
  - platform_engine → platform_db   (PlatformSession)

These engines NEVER share a session, connection pool, or transaction.
No cross-DB queries are permitted anywhere in the application.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.core.config import settings

# ── Auth-service engine ────────────────────────────────────────────────────────
# RULE-01: This engine ONLY connects to the auth_service database.
# It stores hashed SSO tokens and nothing else PII-sensitive.
auth_engine = create_async_engine(
    settings.DATABASE_AUTH_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    # Isolation is kept default (READ COMMITTED) for the auth DB
)

AuthSessionFactory = async_sessionmaker(
    bind=auth_engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# ── Platform engine ────────────────────────────────────────────────────────────
# RULE-01: This engine ONLY connects to the platform_db database.
# auth_token_hash in platform_db has NO FOREIGN KEY to auth_service.
platform_engine = create_async_engine(
    settings.DATABASE_PLATFORM_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
)

PlatformSessionFactory = async_sessionmaker(
    bind=platform_engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# ── Dependency injection ───────────────────────────────────────────────────────

async def get_auth_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async session for the auth_service DB.

    RULE-01: Sessions obtained from this dependency MUST NOT be used to
    query the platform_db schema, and vice-versa.
    """
    async with AuthSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_platform_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async session for the platform_db.

    RULE-01: Sessions obtained from this dependency MUST NOT be used to
    query the auth_service schema, and vice-versa.
    """
    async with PlatformSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Type aliases for cleaner dependency injection signatures
AuthDB = Annotated[AsyncSession, Depends(get_auth_db)]
PlatformDB = Annotated[AsyncSession, Depends(get_platform_db)]


async def dispose_engines() -> None:
    """Dispose both engines gracefully on application shutdown."""
    await auth_engine.dispose()
    await platform_engine.dispose()
