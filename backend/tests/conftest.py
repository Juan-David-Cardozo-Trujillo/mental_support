"""
Backend Tests Configuration

Pytest fixtures and utilities for testing the FastAPI backend
"""

import os
import pytest
from typing import Generator
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient

from backend.main import create_app
from backend.core.database import get_auth_db, get_platform_db
from backend.db.auth_models import AuthBase
from backend.db.platform_models import PlatformBase

# ────────────────────────────────────────────────────────────────────────────
# Database Setup
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def auth_engine():
    """Create test auth database engine."""
    DATABASE_URL = os.getenv(
        "DATABASE_AUTH_URL",
        "postgresql+asyncpg://postgres:postgres@localhost/test_auth"
    )
    
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(AuthBase.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(AuthBase.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture(scope="session")
async def platform_engine():
    """Create test platform database engine."""
    DATABASE_URL = os.getenv(
        "DATABASE_PLATFORM_URL",
        "postgresql+asyncpg://postgres:postgres@localhost/test_platform"
    )
    
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(PlatformBase.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(PlatformBase.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def auth_session(auth_engine):
    """Get test auth database session."""
    async_session = async_sessionmaker(auth_engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def platform_session(platform_engine):
    """Get test platform database session."""
    async_session = async_sessionmaker(platform_engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
        await session.rollback()


# ────────────────────────────────────────────────────────────────────────────
# FastAPI App Setup
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
async def app(auth_session, platform_session):
    """Create test FastAPI application."""
    app = create_app()
    
    # Override database dependencies
    async def override_get_auth_db():
        yield auth_session
    
    async def override_get_platform_db():
        yield platform_session
    
    app.dependency_overrides[get_auth_db] = override_get_auth_db
    app.dependency_overrides[get_platform_db] = override_get_platform_db
    
    yield app
    
    app.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    """Get async HTTP client for testing."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


# ────────────────────────────────────────────────────────────────────────────
# Mock Data Utilities
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_user():
    """Create mock user data."""
    return {
        "profile_id": "123e4567-e89b-12d3-a456-426614174000",
        "role": "student",
        "account_status": "active",
        "consented": True,
    }


@pytest.fixture
def mock_peer_user():
    """Create mock peer counselor."""
    return {
        "profile_id": "223e4567-e89b-12d3-a456-426614174000",
        "role": "peer_counselor",
        "account_status": "active",
        "consented": True,
    }


@pytest.fixture
def mock_professional_user():
    """Create mock professional counselor."""
    return {
        "profile_id": "323e4567-e89b-12d3-a456-426614174000",
        "role": "professional_counselor",
        "account_status": "active",
        "consented": True,
    }


@pytest.fixture
def mock_admin_user():
    """Create mock admin."""
    return {
        "profile_id": "423e4567-e89b-12d3-a456-426614174000",
        "role": "platform_admin",
        "account_status": "active",
        "consented": True,
    }


# ────────────────────────────────────────────────────────────────────────────
# Auth Helpers
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers(mock_user):
    """Get authorization headers with mock user."""
    import json
    from base64 import b64encode
    
    # Simulate JWT token in cookie or header
    return {
        "Authorization": f"Bearer mock-token-{mock_user['profile_id']}"
    }
