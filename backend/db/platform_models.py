"""
SQLAlchemy models for the platform_db (RULE-01).

All 20+ tables live here. The auth_token_hash column in AnonymousProfile
is a plain string — NOT a FK to auth_service. The two databases are
completely separate instances.

CRITICAL: Every table that stores sensitive data uses encrypted bytea fields (AES-256).
No plaintext PII or message content is ever persisted.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── Enum definitions ──────────────────────────────────────────────────────────

class RoleEnum(str, PyEnum):
    """Roles in the system."""
    student = "student"
    peer_counselor = "peer_counselor"
    professional_counselor = "professional_counselor"
    university_admin = "university_admin"
    platform_admin = "platform_admin"


class AccountStatusEnum(str, PyEnum):
    """Account statuses for peer counselors."""
    pending = "pending"
    active = "active"
    suspended = "suspended"
    unavailable = "unavailable"
    inactive = "inactive"


class SupportTypeEnum(str, PyEnum):
    """Types of support requested."""
    peer = "peer"
    professional = "professional"
    resources = "resources"
    all = "all"


class SenderRoleEnum(str, PyEnum):
    """Sender role in chat."""
    student = "student"
    peer_counselor = "peer_counselor"
    professional_counselor = "professional_counselor"
    system = "system"


class SessionStatusEnum(str, PyEnum):
    """Chat session status."""
    active = "active"
    closed = "closed"
    flagged = "flagged"


class AppointmentStatusEnum(str, PyEnum):
    """Appointment status."""
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"


class ContentTypeEnum(str, PyEnum):
    """Resource content type."""
    article = "article"
    video = "video"
    exercise = "exercise"


class ReportStatusEnum(str, PyEnum):
    """Report status."""
    open = "open"
    under_review = "under_review"
    resolved = "resolved"
    dismissed = "dismissed"


class IncidentSeverityEnum(str, PyEnum):
    """Incident severity."""
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IncidentStatusEnum(str, PyEnum):
    """Incident status."""
    open = "open"
    investigating = "investigating"
    resolved = "resolved"


class SupportTypeEnum(str, enum.Enum):
    peer = "peer"
    professional = "professional"
    self_help = "self_help"
    any = "any"


class SessionStatusEnum(str, enum.Enum):
    active = "active"
    closed = "closed"
    flagged = "flagged"


class SenderRoleEnum(str, enum.Enum):
    student = "student"
    peer_counselor = "peer_counselor"
    professional_counselor = "professional_counselor"
    system = "system"


class ReportStatusEnum(str, enum.Enum):
    pending = "pending"
    reviewed = "reviewed"
    dismissed = "dismissed"
    actioned = "actioned"


class ContentTypeEnum(str, enum.Enum):
    article = "article"
    video = "video"
    exercise = "exercise"


class AppointmentStatusEnum(str, enum.Enum):
    requested = "requested"
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"
    no_show = "no_show"


class SeverityEnum(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IncidentStatusEnum(str, enum.Enum):
    open = "open"
    investigating = "investigating"
    resolved = "resolved"
    closed = "closed"


class RetentionPolicyEnum(str, enum.Enum):
    standard = "standard"      # purge 24h after session close
    flagged = "flagged"         # retain 90 days, encrypted, dual-admin access


# ── Declarative Base ──────────────────────────────────────────────────────────

class PlatformBase(DeclarativeBase):
    """Base for all platform_db tables."""
    pass


# ── Models ────────────────────────────────────────────────────────────────────

class AnonymousProfile(PlatformBase):
    """
    Central identity in the platform.

    auth_token_hash is the SHA-256 hash of the SSO token.
    It is NOT a FK to auth_service — it is merely a consistent identifier
    that allows the platform to recognise the same user across sessions
    without storing any PII. (RULE-01)
    """
    __tablename__ = "anonymous_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # RULE-01: NO FK — this is a plain hash string, not a relational reference
    auth_token_hash: Mapped[str] = mapped_column(
        String(256), unique=True, nullable=False, index=True,
        comment="SHA-256 of SSO token. NO FK to auth_service (RULE-01)",
    )
    role: Mapped[str] = mapped_column(
        Enum(RoleEnum, name="role_enum"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # relationships
    consent_record: Mapped[list["ConsentRecord"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    needs_assessments: Mapped[list["NeedsAssessmentResponse"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    peer_counselor_profile: Mapped["PeerCounselorProfile | None"] = relationship(
        back_populates="profile", uselist=False, cascade="all, delete-orphan"
    )
    student_chat_sessions: Mapped[list["ChatSession"]] = relationship(
        foreign_keys="ChatSession.student_profile_id",
        back_populates="student_profile",
    )
    reports_filed: Mapped[list["PeerReport"]] = relationship(
        foreign_keys="PeerReport.reporter_profile_id",
        back_populates="reporter",
    )

    __table_args__ = (
        Index("ix_anon_profile_role", "role"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AnonymousProfile id={self.id} role={self.role}>"


class ConsentRecord(PlatformBase):
    """Tracks informed consent per user (RULE-11)."""
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anonymous_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    consent_version: Mapped[str] = mapped_column(String(20), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ip_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 of client IP — no raw IP stored",
    )

    profile: Mapped["AnonymousProfile"] = relationship(back_populates="consent_record")

    __table_args__ = (
        Index("ix_consent_profile_id", "profile_id"),
    )


class NeedsAssessmentResponse(PlatformBase):
    """Stores anonymised needs-assessment answers."""
    __tablename__ = "needs_assessment_responses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anonymous_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stress_level: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="1-5 scale",
    )
    support_type_preference: Mapped[str] = mapped_column(
        Enum(SupportTypeEnum, name="support_type_enum"), nullable=False
    )
    anonymous_preference: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    # RULE-05: urgency_flag=true → skip queue, create urgent appointment
    urgency_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="If true, skip peer queue and alert all professional counselors (RULE-05)",
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped["AnonymousProfile"] = relationship(back_populates="needs_assessments")

    __table_args__ = (
        Index("ix_needs_profile_id", "profile_id"),
        Index("ix_needs_urgency", "urgency_flag"),
    )


class PeerCounselorProfile(PlatformBase):
    """
    Peer counselor extended profile.

    RULE-02: daily_session_count + sessions_completed enforce the burnout rule.
    RULE-03: report_count_7d + report_window_start enforce auto-suspension.
    """
    __tablename__ = "peer_counselor_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anonymous_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    account_status: Mapped[str] = mapped_column(
        Enum(AccountStatusEnum, name="account_status_enum"),
        nullable=False,
        default=AccountStatusEnum.pending,
        index=True,
    )
    training_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    training_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # RULE-02 counters
    sessions_completed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Cumulative sessions. >= BURNOUT_THRESHOLD → unavailable (RULE-02)",
    )
    daily_session_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Resets at midnight by Celery (RULE-09). Max 3/day (RULE-02)",
    )
    daily_session_reset_date: Mapped[date | None] = mapped_column(
        Date, nullable=True,
        comment="Date of last daily reset",
    )
    available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        index=True,
    )

    # RULE-03 rolling window
    report_count_7d: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Reports received in rolling 7-day window (RULE-03)",
    )
    report_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Start of current 7-day report window",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped["AnonymousProfile"] = relationship(back_populates="peer_counselor_profile")
    peer_chat_sessions: Mapped[list["ChatSession"]] = relationship(
        foreign_keys="ChatSession.peer_counselor_profile_id",
        back_populates="peer_counselor_profile",
    )
    reports_received: Mapped[list["PeerReport"]] = relationship(
        foreign_keys="PeerReport.reported_peer_id",
        back_populates="reported_peer",
    )
    training_completions: Mapped[list["TrainingCompletion"]] = relationship(
        back_populates="peer_profile"
    )
    badges: Mapped[list["RecognitionBadge"]] = relationship(back_populates="peer_profile")

    __table_args__ = (
        Index("ix_peer_status_available", "account_status", "available"),
        Index("ix_peer_sessions_completed", "sessions_completed"),
    )


class ProfessionalCounselor(PlatformBase):
    """
    Professional counselor provisioned by an admin.

    Name and email are AES-256-GCM encrypted at rest (RULE-01 privacy).
    """
    __tablename__ = "professional_counselors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provisioned_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anonymous_profiles.id"),
        nullable=False,
    )
    encrypted_name: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False,
        comment="AES-256-GCM encrypted display name",
    )
    encrypted_email: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False,
        comment="AES-256-GCM encrypted email address",
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    availability_slots: Mapped[list["CounselorAvailability"]] = relationship(
        back_populates="counselor"
    )
    appointments: Mapped[list["Appointment"]] = relationship(
        foreign_keys="Appointment.counselor_id",
        back_populates="counselor",
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        foreign_keys="ChatSession.professional_counselor_id",
        back_populates="professional_counselor",
    )


class CounselorAvailability(PlatformBase):
    """
    Availability slot for professional counselors.

    RULE-07: Slot is locked with SELECT … FOR UPDATE to prevent double-booking.
    """
    __tablename__ = "counselor_availability"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    counselor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("professional_counselors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    available_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    available_to: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    # RULE-07: This field is set to True under row-level lock
    booked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    counselor: Mapped["ProfessionalCounselor"] = relationship(
        back_populates="availability_slots"
    )
    appointment: Mapped["Appointment | None"] = relationship(
        foreign_keys="Appointment.availability_slot_id",
        back_populates="slot",
        uselist=False,
    )

    __table_args__ = (
        Index("ix_avail_counselor_from", "counselor_id", "available_from"),
        Index("ix_avail_booked", "booked"),
    )


class ChatSession(PlatformBase):
    """A chat session between a student and a peer/professional counselor."""
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anonymous_profiles.id"),
        nullable=False,
        index=True,
    )
    peer_counselor_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("peer_counselor_profiles.id"),
        nullable=True,
        index=True,
    )
    professional_counselor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("professional_counselors.id"),
        nullable=True,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    session_status: Mapped[str] = mapped_column(
        Enum(SessionStatusEnum, name="session_status_enum"),
        nullable=False,
        default=SessionStatusEnum.active,
        index=True,
    )
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    student_profile: Mapped["AnonymousProfile"] = relationship(
        foreign_keys=[student_profile_id],
        back_populates="student_chat_sessions",
    )
    peer_counselor_profile: Mapped["PeerCounselorProfile | None"] = relationship(
        foreign_keys=[peer_counselor_profile_id],
        back_populates="peer_chat_sessions",
    )
    professional_counselor: Mapped["ProfessionalCounselor | None"] = relationship(
        foreign_keys=[professional_counselor_id],
        back_populates="chat_sessions",
    )
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    reports: Mapped[list["PeerReport"]] = relationship(back_populates="session")
    feedback: Mapped["Feedback | None"] = relationship(
        foreign_keys="Feedback.session_id",
        back_populates="session",
        uselist=False,
    )

    __table_args__ = (
        Index("ix_session_student_status", "student_profile_id", "session_status"),
        Index("ix_session_peer_status", "peer_counselor_profile_id", "session_status"),
    )


class ChatMessage(PlatformBase):
    """
    Encrypted chat message.

    RULE-06: retention_policy determines deletion schedule.
    - standard: purge 24h after session close.
    - flagged: retain 90 days, encrypted, dual-admin access required.
    """
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_role: Mapped[str] = mapped_column(
        Enum(SenderRoleEnum, name="sender_role_enum"), nullable=False
    )
    # All message content is AES-256-GCM encrypted — never stored as plaintext
    encrypted_content: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False,
        comment="AES-256-GCM ciphertext. NEVER store plaintext here.",
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retention_policy: Mapped[str] = mapped_column(
        Enum(RetentionPolicyEnum, name="retention_policy_enum"),
        nullable=False,
        default=RetentionPolicyEnum.standard,
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_msg_session_sent", "session_id", "sent_at"),
        Index("ix_msg_retention", "retention_policy", "sent_at"),
    )


class PeerReport(PlatformBase):
    """
    Report filed against a peer counselor.

    RULE-03: 3 reports in 7-day window → auto-suspension.
    """
    __tablename__ = "peer_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id"),
        nullable=False,
        index=True,
    )
    reporter_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anonymous_profiles.id"),
        nullable=False,
    )
    reported_peer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("peer_counselor_profiles.id"),
        nullable=False,
        index=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        Enum(ReportStatusEnum, name="report_status_enum"),
        nullable=False,
        default=ReportStatusEnum.pending,
    )

    session: Mapped["ChatSession"] = relationship(back_populates="reports")
    reporter: Mapped["AnonymousProfile"] = relationship(
        foreign_keys=[reporter_profile_id],
        back_populates="reports_filed",
    )
    reported_peer: Mapped["PeerCounselorProfile"] = relationship(
        foreign_keys=[reported_peer_id],
        back_populates="reports_received",
    )

    __table_args__ = (
        Index("ix_report_peer_submitted", "reported_peer_id", "submitted_at"),
    )


class Appointment(PlatformBase):
    """Appointment with a professional counselor."""
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anonymous_profiles.id"),
        nullable=False,
        index=True,
    )
    counselor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("professional_counselors.id"),
        nullable=False,
        index=True,
    )
    availability_slot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("counselor_availability.id"),
        nullable=False,
        unique=True,  # one appointment per slot
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Enum(AppointmentStatusEnum, name="appointment_status_enum"),
        nullable=False,
        default=AppointmentStatusEnum.requested,
        index=True,
    )
    # RULE-05: urgent appointments skip the queue
    urgency_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )

    student_profile: Mapped["AnonymousProfile"] = relationship(
        foreign_keys=[student_profile_id]
    )
    counselor: Mapped["ProfessionalCounselor"] = relationship(
        foreign_keys=[counselor_id], back_populates="appointments"
    )
    slot: Mapped["CounselorAvailability"] = relationship(
        foreign_keys=[availability_slot_id], back_populates="appointment"
    )
    feedback: Mapped["Feedback | None"] = relationship(
        foreign_keys="Feedback.appointment_id",
        back_populates="appointment",
        uselist=False,
    )

    __table_args__ = (
        Index("ix_appt_student_status", "student_profile_id", "status"),
        Index("ix_appt_scheduled", "scheduled_time"),
        Index("ix_appt_urgency", "urgency_flag", "status"),
    )


class Resource(PlatformBase):
    """Self-help resource (article/video/exercise)."""
    __tablename__ = "resources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(
        Enum(ContentTypeEnum, name="content_type_enum"), nullable=False
    )
    url_or_path: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anonymous_profiles.id"),
        nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    # RULE-10: public share token — access_count is incremented with NO user logging
    public_share_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_resource_category_active", "category", "active"),
        Index("ix_resource_token", "public_share_token"),
    )


class Feedback(PlatformBase):
    """Post-session / post-appointment anonymous feedback."""
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id"),
        nullable=True,
        index=True,
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id"),
        nullable=True,
        index=True,
    )
    match_quality_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    support_quality_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anonymity_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_satisfaction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["ChatSession | None"] = relationship(
        foreign_keys=[session_id], back_populates="feedback"
    )
    appointment: Mapped["Appointment | None"] = relationship(
        foreign_keys=[appointment_id], back_populates="feedback"
    )

    __table_args__ = (
        CheckConstraint(
            "(session_id IS NOT NULL) OR (appointment_id IS NOT NULL)",
            name="ck_feedback_has_reference",
        ),
        CheckConstraint(
            "match_quality_rating IS NULL OR (match_quality_rating >= 1 AND match_quality_rating <= 5)",
            name="ck_match_quality_range",
        ),
        CheckConstraint(
            "support_quality_rating IS NULL OR (support_quality_rating >= 1 AND support_quality_rating <= 5)",
            name="ck_support_quality_range",
        ),
        CheckConstraint(
            "overall_satisfaction IS NULL OR (overall_satisfaction >= 1 AND overall_satisfaction <= 5)",
            name="ck_overall_satisfaction_range",
        ),
    )


class AcademicCalendarPeak(PlatformBase):
    """Tracks high-demand academic periods (exam weeks, etc.)."""
    __tablename__ = "academic_calendar_peaks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    period_name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    notification_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_peak_dates", "start_date", "end_date"),
    )


class TrainingModule(PlatformBase):
    """Training content for peer counselors."""
    __tablename__ = "training_modules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    completions: Mapped[list["TrainingCompletion"]] = relationship(back_populates="module")


class TrainingCompletion(PlatformBase):
    """Records a peer counselor's training attempt and result."""
    __tablename__ = "training_completions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    peer_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("peer_counselor_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_modules.id"),
        nullable=False,
        index=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    peer_profile: Mapped["PeerCounselorProfile"] = relationship(
        back_populates="training_completions"
    )
    module: Mapped["TrainingModule"] = relationship(back_populates="completions")


class RecognitionBadge(PlatformBase):
    """Awarded to peer counselors at milestone completions (10/25/50/100)."""
    __tablename__ = "recognition_badges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    peer_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("peer_counselor_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    badge_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="e.g. 'sessions_10', 'sessions_25', 'sessions_50', 'sessions_100'",
    )
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    peer_profile: Mapped["PeerCounselorProfile"] = relationship(back_populates="badges")

    __table_args__ = (
        UniqueConstraint("peer_profile_id", "badge_type", name="uq_peer_badge"),
    )


class SystemMetric(PlatformBase):
    """Time-series system metrics for monitoring and surge detection."""
    __tablename__ = "system_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_metric_name_time", "metric_name", "recorded_at"),
    )


class Incident(PlatformBase):
    """Tracks system incidents (escalations, suspensions, etc.)."""
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(
        Enum(SeverityEnum, name="severity_enum"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Enum(IncidentStatusEnum, name="incident_status_enum"),
        nullable=False,
        default=IncidentStatusEnum.open,
        index=True,
    )

    __table_args__ = (
        Index("ix_incident_type_severity", "incident_type", "severity"),
        Index("ix_incident_status_reported", "status", "reported_at"),
    )
