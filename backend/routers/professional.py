"""
Professional Counselor Router
=============================

Professional counselor-specific endpoints:
- View appointment schedule
- Manage availability slots
- Session management
- Performance metrics

Endpoints:
  GET  /professional/schedule       → Counselor's appointment schedule
  POST /professional/availability   → Add availability slot
  DELETE /professional/availability/{id} → Remove availability slot
  GET  /professional/appointments   → Upcoming appointments
  GET  /professional/metrics        → Performance metrics
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from backend.core.database import get_platform_db
from backend.core.security import get_current_user, require_role
from backend.db.platform_models import (
    ProfessionalCounselor,
    CounselorAvailability,
    Appointment,
    Feedback,
    AppointmentStatusEnum,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/professional", tags=["Professional Counselor"])

# ──────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────────────────────────────────────

class AvailabilitySlotCreate(BaseModel):
    """Add availability slot."""
    slot_start: datetime = Field(..., description="Slot start datetime")
    slot_end: datetime = Field(..., description="Slot end datetime")
    max_capacity: int = Field(default=1, description="Max concurrent sessions (usually 1)")


class AvailabilitySlotResponse(BaseModel):
    """Availability slot details."""
    id: str
    slot_start: datetime
    slot_end: datetime
    is_available: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class AppointmentItem(BaseModel):
    """Appointment in counselor's schedule."""
    id: str
    student_id: str
    appointment_datetime: datetime
    status: str
    urgency_flag: bool
    reason_for_visit: Optional[str] = None
    confirmed_at: Optional[datetime]


class PerformanceMetrics(BaseModel):
    """Counselor performance metrics."""
    total_appointments_completed: int
    average_student_rating: Optional[float]
    total_sessions: int
    session_feedback_count: int
    repeat_student_rate: Optional[float]
    avg_appointment_duration_minutes: Optional[float]
    cancellation_rate: Optional[float]


class CounselorScheduleResponse(BaseModel):
    """Counselor schedule overview."""
    counselor_id: str
    total_slots_available: int
    booked_appointments: int
    availability_percentage: float
    upcoming_appointments: list[AppointmentItem]
    metrics: PerformanceMetrics


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/schedule", response_model=CounselorScheduleResponse)
async def get_counselor_schedule(
    days_ahead: int = 30,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("professional_counselor")),
):
    """
    Get counselor's schedule overview for next N days.
    
    Includes:
    - Available slots
    - Booked appointments
    - Performance metrics
    """
    try:
        counselor_id = current_user["profile_id"]
        
        # Verify counselor exists
        counselor_result = await db.execute(
            select(ProfessionalCounselor).where(
                ProfessionalCounselor.id == counselor_id
            )
        )
        counselor = counselor_result.scalar_one_or_none()
        
        if not counselor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Counselor profile not found"
            )
        
        now = datetime.now(timezone.utc)
        future_date = now + timedelta(days=days_ahead)
        
        # Count total available slots
        slots_result = await db.execute(
            select(func.count(CounselorAvailability.id)).where(
                and_(
                    CounselorAvailability.counselor_id == counselor_id,
                    CounselorAvailability.slot_start > now,
                    CounselorAvailability.slot_start < future_date,
                )
            )
        )
        total_slots = slots_result.scalar() or 0
        
        # Count booked appointments
        booked_result = await db.execute(
            select(func.count(Appointment.id)).where(
                and_(
                    Appointment.counselor_id == counselor_id,
                    Appointment.status == "confirmed",
                    Appointment.scheduled_time > now,
                    Appointment.scheduled_time < future_date,
                )
            )
        )
        booked_count = booked_result.scalar() or 0
        
        # Get upcoming appointments
        appts_result = await db.execute(
            select(Appointment).where(
                and_(
                    Appointment.counselor_id == counselor_id,
                    Appointment.scheduled_time > now,
                    Appointment.scheduled_time < future_date,
                )
            ).order_by(
                Appointment.scheduled_time.asc()
            )
        )
        appointments = appts_result.scalars().all()
        
        appt_items = [
            AppointmentItem(
                id=str(a.id),
                student_id=str(a.student_profile_id),
                appointment_datetime=a.scheduled_time,
                status=a.status,
                urgency_flag=a.urgency_flag,
                reason_for_visit=None,
                confirmed_at=a.confirmed_at,
            )
            for a in appointments
        ]
        
        # Calculate metrics
        completed_result = await db.execute(
            select(func.count(Appointment.id)).where(
                and_(
                    Appointment.counselor_id == counselor_id,
                    Appointment.status == "completed",
                )
            )
        )
        completed_count = completed_result.scalar() or 0
        
        # Average rating
        rating_result = await db.execute(
            select(func.avg(Feedback.overall_satisfaction))
            .select_from(Feedback)
            .join(Appointment)
            .where(Appointment.counselor_id == counselor_id)
        )
        avg_rating = rating_result.scalar()
        
        # Total sessions
        sessions_result = await db.execute(
            select(func.count(Appointment.id)).where(
                Appointment.counselor_id == counselor_id
            )
        )
        total_sessions = sessions_result.scalar() or 0
        
        # Feedback count
        feedback_result = await db.execute(
            select(func.count(Feedback.id))
            .select_from(Feedback)
            .join(Appointment)
            .where(Appointment.counselor_id == counselor_id)
        )
        feedback_count = feedback_result.scalar() or 0
        
        metrics = PerformanceMetrics(
            total_appointments_completed=completed_count,
            average_student_rating=float(avg_rating) if avg_rating else None,
            total_sessions=total_sessions,
            session_feedback_count=feedback_count,
            repeat_student_rate=None,  # TODO: calculate
            avg_appointment_duration_minutes=None,  # TODO: calculate
            cancellation_rate=None,  # TODO: calculate
        )
        
        availability_pct = (total_slots - booked_count) / max(total_slots, 1) * 100
        
        schedule = CounselorScheduleResponse(
            counselor_id=str(counselor_id),
            total_slots_available=total_slots,
            booked_appointments=booked_count,
            availability_percentage=availability_pct,
            upcoming_appointments=appt_items,
            metrics=metrics,
        )
        
        logger.info(f"✓ Schedule retrieved for counselor {counselor_id}")
        return schedule
        
    except Exception as e:
        logger.error(f"✗ Error retrieving schedule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve schedule"
        )


@router.post("/availability", response_model=AvailabilitySlotResponse, status_code=status.HTTP_201_CREATED)
async def add_availability(
    req: AvailabilitySlotCreate,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("professional_counselor")),
):
    """
    Add availability slot to counselor's schedule.
    
    Request Body:
    - slot_start: When the slot begins
    - slot_end: When the slot ends
    - max_capacity: Max concurrent sessions (usually 1 per counselor)
    """
    try:
        counselor_id = current_user["profile_id"]
        
        # Validate time range
        if req.slot_end <= req.slot_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="slot_end must be after slot_start"
            )
        
        # Check for overlapping slots
        overlap_result = await db.execute(
            select(CounselorAvailability).where(
                and_(
                    CounselorAvailability.counselor_id == counselor_id,
                    CounselorAvailability.slot_start < req.slot_end,
                    CounselorAvailability.slot_end > req.slot_start,
                )
            )
        )
        
        if overlap_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Overlapping availability slot already exists"
            )
        
        # Create availability slot
        slot = CounselorAvailability(
            id=uuid.uuid4(),
            counselor_id=uuid.UUID(counselor_id),
            slot_start=req.slot_start,
            slot_end=req.slot_end,
            booked=False,
            created_at=datetime.now(timezone.utc),
        )
        
        db.add(slot)
        await db.commit()
        await db.refresh(slot)
        
        logger.info(
            f"✓ Availability slot added for counselor {counselor_id}: "
            f"{req.slot_start} - {req.slot_end}"
        )
        return AvailabilitySlotResponse.from_orm(slot)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"✗ Error adding availability: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add availability slot"
        )


@router.delete("/availability/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_availability(
    slot_id: str,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("professional_counselor")),
):
    """Delete availability slot."""
    try:
        counselor_id = current_user["profile_id"]
        slot_uuid = uuid.UUID(slot_id)
        
        slot_result = await db.execute(
            select(CounselorAvailability).where(
                and_(
                    CounselorAvailability.id == slot_uuid,
                    CounselorAvailability.counselor_id == counselor_id,
                )
            )
        )
        slot = slot_result.scalar_one_or_none()
        
        if not slot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Availability slot not found"
            )
        
        await db.delete(slot)
        await db.commit()
        
        logger.info(f"✓ Availability slot deleted: {slot_id}")
        return None
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid slot ID format"
        )


@router.get("/appointments", response_model=list[AppointmentItem])
async def get_upcoming_appointments(
    days_ahead: int = 30,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("professional_counselor")),
):
    """Get counselor's upcoming appointments."""
    try:
        counselor_id = current_user["profile_id"]
        now = datetime.now(timezone.utc)
        future_date = now + timedelta(days=days_ahead)
        
        query = select(Appointment).where(
            and_(
                Appointment.counselor_id == counselor_id,
                Appointment.scheduled_time > now,
                Appointment.scheduled_time < future_date,
            )
        )
        
        if status_filter:
            query = query.where(Appointment.status == status_filter)
        
        query = query.order_by(Appointment.scheduled_time.asc())
        
        result = await db.execute(query)
        appointments = result.scalars().all()
        
        return [
            AppointmentItem(
                id=str(a.id),
                student_id=str(a.student_profile_id),
                appointment_datetime=a.scheduled_time,
                status=a.status,
                urgency_flag=a.urgency_flag,
                reason_for_visit=None,
                confirmed_at=a.confirmed_at,
            )
            for a in appointments
        ]
        
    except Exception as e:
        logger.error(f"✗ Error retrieving appointments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve appointments"
        )


@router.get("/metrics", response_model=PerformanceMetrics)
async def get_performance_metrics(
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("professional_counselor")),
):
    """Get counselor's performance metrics."""
    try:
        counselor_id = current_user["profile_id"]
        
        # Completed appointments
        completed_result = await db.execute(
            select(func.count(Appointment.id)).where(
                and_(
                    Appointment.counselor_id == counselor_id,
                    Appointment.status == "completed",
                )
            )
        )
        completed_count = completed_result.scalar() or 0
        
        # Average rating
        rating_result = await db.execute(
            select(func.avg(Feedback.rating)).where(
                Feedback.counselor_id == counselor_id
            )
        )
        avg_rating = rating_result.scalar()
        
        # Total sessions
        sessions_result = await db.execute(
            select(func.count(Appointment.id)).where(
                Appointment.counselor_id == counselor_id
            )
        )
        total_sessions = sessions_result.scalar() or 0
        
        # Feedback count
        feedback_result = await db.execute(
            select(func.count(Feedback.id))
            .select_from(Feedback)
            .join(Appointment)
            .where(Appointment.counselor_id == counselor_id)
        )
        feedback_count = feedback_result.scalar() or 0
        
        return PerformanceMetrics(
            total_appointments_completed=completed_count,
            average_student_rating=float(avg_rating) if avg_rating else None,
            total_sessions=total_sessions,
            session_feedback_count=feedback_count,
            repeat_student_rate=None,
            avg_appointment_duration_minutes=None,
            cancellation_rate=None,
        )
        
    except Exception as e:
        logger.error(f"✗ Error retrieving metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve metrics"
        )
