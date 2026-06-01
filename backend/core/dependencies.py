"""
FastAPI dependency injection and database session factories.
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import AuthSessionFactory, PlatformSessionFactory


async def get_auth_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provides an AsyncSession for the auth_service database.
    Used for reading/writing auth tokens.
    """
    async with AuthSessionFactory() as session:
        yield session


async def get_platform_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provides an AsyncSession for the platform_db database.
    Used for all platform data (profiles, chats, appointments, etc.).
    """
    async with PlatformSessionFactory() as session:
        yield session
