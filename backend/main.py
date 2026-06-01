"""
Main FastAPI application for the Student Mental Health Support Platform.

This is the application factory that:
1. Initializes FastAPI with ASGI middleware stack
2. Sets up Redis connection for session/cache management
3. Registers all routers (auth, assessment, matching, chat, etc.)
4. Configures error handlers and health checks
5. Implements lifespan events for startup/shutdown

RULE-01: Zero-knowledge architecture is maintained through:
  - Completely separate auth_service and platform_db connections
  - Dependency injection ensures per-request session isolation
  - Middleware does not perform cross-database queries
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZIPMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import pool
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.config import settings
from backend.core.security import RateLimitMiddleware, SessionInactivityMiddleware

logger = logging.getLogger(__name__)


# ── Lifespan context ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan: startup and shutdown events.

    Startup:
    - Connect to Redis for session management, caching, and message queue
    - Create database tables (alembic migrations in production)

    Shutdown:
    - Gracefully close Redis connections
    - Close database connection pools
    """
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("🚀 Starting Mental Health Platform backend...")

    # Connect to Redis
    try:
        redis = aioredis.from_url(settings.REDIS_URL, encoding="utf8", decode_responses=True)
        await redis.ping()
        app.state.redis = redis
        logger.info("✓ Connected to Redis")
    except Exception as exc:
        logger.error(f"✗ Failed to connect to Redis: {exc}")
        raise

    # Create database tables (development only; use Alembic in production)
    if settings.DEBUG:
        try:
            from backend.core.database import auth_engine, platform_engine
            from backend.db.auth_models import AuthBase
            from backend.db.platform_models import PlatformBase

            async with auth_engine.begin() as conn:
                await conn.run_sync(AuthBase.metadata.create_all)
            async with platform_engine.begin() as conn:
                await conn.run_sync(PlatformBase.metadata.create_all)
            logger.info("✓ Database tables initialized")
        except Exception as exc:
            logger.error(f"✗ Failed to initialize database: {exc}")
            raise

    logger.info("✓ Platform backend ready")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("⏹️  Shutting down Mental Health Platform backend...")

    if hasattr(app.state, "redis"):
        await app.state.redis.close()
        logger.info("✓ Redis connection closed")

    try:
        from backend.core.database import auth_engine, platform_engine
        await auth_engine.dispose()
        await platform_engine.dispose()
        logger.info("✓ Database connections closed")
    except Exception as exc:
        logger.warning(f"⚠ Error closing databases: {exc}")

    logger.info("✓ Shutdown complete")


# ── Application factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Architecture:
    - Global error handlers for HTTPException and generic exceptions
    - CORS for frontend development (restrict in production)
    - GZIP compression for responses
    - Rate limiting and session inactivity middleware
    - Health check endpoint
    - All routers mounted at /api/v1 prefix
    """
    app = FastAPI(
        title="Student Mental Health Support Platform",
        description="Privacy-first peer and professional counseling platform",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── Global error handlers ─────────────────────────────────────────────────

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """
        Format HTTPException responses with {error: {code, message}} structure.
        """
        if isinstance(exc.detail, dict):
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": exc.detail},
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "HTTP_ERROR", "message": exc.detail}},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Catch-all for unhandled exceptions. Log and return 500.
        """
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred. Please try again later.",
                }
            },
        )

    # ── Middleware stack ──────────────────────────────────────────────────────

    # CORS: Allow frontend in development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count"],  # for pagination
    )

    # GZIP compression
    app.add_middleware(GZIPMiddleware, minimum_size=1000)

    # Security middleware (applied in reverse order)
    app.add_middleware(SessionInactivityMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # ── Health check endpoint ─────────────────────────────────────────────────

    @app.get("/health", tags=["System"])
    async def health_check() -> dict[str, Any]:
        """
        Simple health check endpoint.
        Returns 200 if the server is running.
        """
        return {"status": "ok"}

    @app.get("/health/ready", tags=["System"])
    async def readiness_check(request: Request) -> dict[str, Any]:
        """
        Readiness probe: checks dependencies (Redis, databases).
        Used by Kubernetes/ECS health checks.
        """
        checks = {
            "database": "unknown",
            "redis": "unknown",
        }

        # Check Redis
        redis: aioredis.Redis | None = getattr(request.app.state, "redis", None)
        try:
            if redis:
                await redis.ping()
                checks["redis"] = "ok"
            else:
                checks["redis"] = "unavailable"
        except Exception as exc:
            logger.warning(f"Redis health check failed: {exc}")
            checks["redis"] = "error"

        # Check databases (simple ping via connection pool)
        try:
            from backend.core.database import auth_engine, platform_engine

            async with auth_engine.connect() as conn:
                await conn.execute("SELECT 1")
            async with platform_engine.connect() as conn:
                await conn.execute("SELECT 1")
            checks["database"] = "ok"
        except Exception as exc:
            logger.warning(f"Database health check failed: {exc}")
            checks["database"] = "error"

        # Return 503 if any dependency is down
        status_code = status.HTTP_200_OK if all(v == "ok" for v in checks.values()) else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(content={"checks": checks}, status_code=status_code)

    # ── API routes ────────────────────────────────────────────────────────────

    from backend.routers import (
        auth,
        assessment,
        matching,
        chat,
        appointments,
        resources,
        peer,
        professional,
    )

    api_v1_prefix = "/api/v1"
    
    # Priority 1: Core modules
    app.include_router(auth.router, prefix=api_v1_prefix)
    app.include_router(assessment.router, prefix=api_v1_prefix)
    app.include_router(matching.router, prefix=api_v1_prefix)
    app.include_router(chat.router, prefix=api_v1_prefix)
    
    # Priority 2: MVP modules
    app.include_router(appointments.router, prefix=api_v1_prefix)
    app.include_router(resources.router, prefix=api_v1_prefix)
    app.include_router(peer.router, prefix=api_v1_prefix)
    app.include_router(professional.router, prefix=api_v1_prefix)

    return app


# ── Application instance ──────────────────────────────────────────────────────

app = create_app()
