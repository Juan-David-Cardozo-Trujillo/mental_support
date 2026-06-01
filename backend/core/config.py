"""
Core configuration using Pydantic Settings.
Loads all settings from environment variables or .env file.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    # RULE-01: auth_service DB and platform_db are completely separate.
    DATABASE_AUTH_URL: str = Field(
        default="postgresql+asyncpg://auth_user:auth_pass@localhost:5432/auth_service_db",
        description="DSN for the authentication-service database (ZERO-KNOWLEDGE: separate from platform)",
    )
    DATABASE_PLATFORM_URL: str = Field(
        default="postgresql+asyncpg://platform_user:platform_pass@localhost:5433/platform_db",
        description="DSN for the main platform database",
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET: str = Field(default="CHANGE_ME_IN_PRODUCTION_jwt_secret_at_least_32_chars")
    JWT_EXPIRE_HOURS: int = Field(default=8)
    JWT_ALGORITHM: str = Field(default="HS256")

    # ── Encryption ────────────────────────────────────────────────────────────
    # 32-byte hex string (64 hex chars) = 256 bits for AES-256
    AES_KEY: str = Field(
        default="0" * 64,
        description="32-byte AES key as hex string (64 hex characters)",
    )

    # ── SSO (OAuth2 / OIDC) ───────────────────────────────────────────────────
    SSO_CLIENT_ID: str = Field(default="mental_health_client")
    SSO_CLIENT_SECRET: str = Field(default="CHANGE_ME_IN_PRODUCTION")
    SSO_AUTHORIZATION_URL: str = Field(
        default="https://sso.university.edu/oauth/authorize"
    )
    SSO_TOKEN_URL: str = Field(
        default="https://sso.university.edu/oauth/token"
    )
    SSO_REDIRECT_URI: str = Field(
        default="http://localhost:8000/auth/sso/callback"
    )

    # ── Business Rules ────────────────────────────────────────────────────────
    # RULE-02: Peer burnout thresholds
    BURNOUT_THRESHOLD: int = Field(
        default=20,
        description="Cumulative sessions before peer is set unavailable (RULE-02)",
    )
    MAX_DAILY_SESSIONS: int = Field(
        default=3,
        description="Maximum sessions a peer counselor can handle per day (RULE-02)",
    )

    # Training
    TRAINING_PASS_SCORE: int = Field(
        default=70,
        description="Minimum score (percent) to pass training module",
    )

    # RULE-03: Auto-suspension
    REPORT_SUSPENSION_THRESHOLD: int = Field(
        default=3,
        description="Reports in rolling window that trigger suspension (RULE-03)",
    )
    REPORT_WINDOW_DAYS: int = Field(
        default=7,
        description="Rolling window in days for report count (RULE-03)",
    )

    # RULE-06: Message retention
    MESSAGE_PURGE_HOURS: int = Field(
        default=24,
        description="Hours after session close before non-flagged messages are purged (RULE-06)",
    )
    FLAGGED_RETENTION_DAYS: int = Field(
        default=90,
        description="Days to retain messages from flagged sessions (RULE-06)",
    )

    # RULE-13: Surge detection
    SURGE_MULTIPLIER: float = Field(
        default=2.0,
        description="Arrival rate multiplier to trigger surge protocol (RULE-13)",
    )
    QUEUE_CHECK_NORMAL_SECONDS: int = Field(default=60)
    QUEUE_CHECK_SURGE_SECONDS: int = Field(default=30)
    QUEUE_WAIT_ESCALATION_SECONDS: int = Field(default=900)

    # Session inactivity
    SESSION_INACTIVITY_SECONDS: int = Field(
        default=1800,
        description="Seconds of inactivity before session is expired (30 min)",
    )

    # RULE-12: Privacy reminder every N messages
    PRIVACY_REMINDER_INTERVAL: int = Field(
        default=10,
        description="Inject privacy reminder to student every N messages (RULE-12)",
    )

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2")

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = Field(default=100)
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60)

    # ── Cors ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "https://mentalhealth.university.edu"]
    )

    # ── Misc ──────────────────────────────────────────────────────────────────
    APP_TITLE: str = Field(default="Student Mental Health Support Platform")
    APP_VERSION: str = Field(default="1.0.0")
    DEBUG: bool = Field(default=False)
    ENVIRONMENT: str = Field(default="development")

    @property
    def SSO_CALLBACK_URL(self) -> str:
        """Full callback URL for SSO redirect."""
        return self.SSO_REDIRECT_URI


settings = Settings()
