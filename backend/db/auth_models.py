"""
SQLAlchemy models for the auth_service database (RULE-01).

This module ONLY defines the AuthToken model used by the authentication
service. It lives in its own database instance, completely isolated from
the platform_db. No join or foreign key reference to platform tables exists
here or anywhere else.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class AuthBase(DeclarativeBase):
    """Base for all auth_service tables."""
    pass


class AuthToken(AuthBase):
    """
    Stores hashed SSO tokens.

    The raw SSO token is NEVER stored. Only its SHA-256 hex digest is
    persisted here so that even if this table is compromised, no user
    identity can be recovered from it.

    RULE-01: This table has absolutely no FK or logical reference to any
    platform_db table. The auth_token_hash value appears in platform_db's
    AnonymousProfile purely by coincidence of the hashing process; there
    is no relational join.
    """

    __tablename__ = "auth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(256),
        unique=True,
        nullable=False,
        index=True,
        comment="SHA-256 hex digest of the raw SSO token",
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Role assigned at SSO: student | peer_counselor | professional_counselor | admin",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
        comment="Updated on every successful JWT verification",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuthToken id={self.id} role={self.role}>"
