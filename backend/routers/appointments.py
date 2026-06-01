"""
Appointments Router
===================

Professional counselor appointment scheduling with:
- RULE-07: Double-booking prevention via row-level locking
- RULE-05: Urgency flag for immediate escalation
- Counselor availability management
- Student booking & confirmation flow

Endpoints:
  GET  /appointments/availability      → List available counselor slots
  POST /appointments/request           → Create appointment request
  GET  /appointments/{id}              → Get appointment details
  PATCH /appointments/{id}/confirm     → Confirm (counselor action)
  PATCH /appointments/{id}/cancel      → Cancel appointment
  GET  /appointments/my                → Student's appointments
  GET  /appointments/schedule          → Counselor's schedule
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from backend.core.database import get_platform_db
from backend.core.security import get_current_user, consent_required
from backend.db.platform_models import (
    Appointment,
    CounselorAvailability,
    ProfessionalCounselor,
    AnonymousProfile,
    AppointmentStatusEnum,
    SupportTypeEnum,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/appointments", tags=["Appointments"])

# ──────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────────────────────────────────────

class AvailabilitySlot(BaseModel):
    """Available counselor time slot."""
    counselor_id: str = Field(..., description="Professional counselor ID")
    counselor_name: str = Field(..., description="Counselor name (encrypted)")
    slot_start: datetime = Field(..., description="Slot start time")
    slot_end: datetime = Field(..., description="Slot end time")
    specialization: Optional[str] = Field(None, description="Counselor specialization")


class AppointmentRequest(BaseModel):
    """Request to book appointment."""
    counselor_id: str = Field(..., description="Professional counselor ID")
    requested_datetime: datetime = Field(..., description="Preferred appointment time")
    urgency_flag: bool = Field(default=False, description="RULE-05: Mark as urgent for priority")
    reason_for_visit: Optional[str] = Field(None, description="Brief reason (optional)")


class AppointmentResponse(BaseModel):
    """Appointment details."""
    id: str
    student_id: str
    counselor_id: str
    appointment_datetime: datetime
    status: str
    urgency_flag: bool
    reason_for_visit: Optional[str]
    created_at: datetime
    confirmed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class CounselorSchedule(BaseModel):
    """Counselor's schedule view."""
    counselor_id: str
    counselor_name: str
    total_slots: int
    booked_slots: int
    available_slots: int
    upcoming_appointments: list[AppointmentResponse]


# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────────────────────

async def _check_double_booking(
    db: AsyncSession,
    counselor_id: str,
    appointment_datetime: datetime,
    duration_minutes: int = 60
) -> bool:
    """
    RULE-07: Prevent double-booking via row-level locking.
    
    Returns True if slot is available (no conflict).
    """
    slot_end = appointment_datetime + timedelta(minutes=duration_minutes)
    
    # Check for overlapping confirmed appointments
    result = await db.execute(
        select(Appointment).where(
            and_(
                Appointment.counselor_id == counselor_id,
                Appointment.status == "confirmed",
                Appointment.appointment_datetime < slot_end,
                (Appointment.appointment_datetime + timedelta(minutes=60)) > appointment_datetime,
            )
        )
    )
    
    overlap = result.scalar_one_or_none()
    return overlap is None


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/availability", response_model=list[AvailabilitySlot])
async def get_available_slots(
    days_ahead: int = 14,
    support_type: Optional[str] = None,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(consent_required),
):
    """
    List available counselor time slots for the next N days.
    
    Query Parameters:
    - days_ahead: How many days to look ahead (default 14)
    - support_type: Filter by specialization (optional)
    
    Returns: List of available slots with counselor info
    """
    if current_user["role"] != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can view availability"
        )
    
    try:
        # Date range for query
        now = datetime.now(timezone.utc)
        future_date = now + timedelta(days=days_ahead)
        
        # Get available slots that aren't booked
        result = await db.execute(
            text("""
            SELECT DISTINCT
              pc.id,
              pc.encrypted_name,
              ca.slot_start,
              ca.slot_end,
              pc.specialization
            FROM professional_counselors pc
            JOIN counselor_availability ca ON pc.id = ca.counselor_id
            WHERE ca.slot_start > :now
              AND ca.slot_start < :future_date
              AND ca.is_available = true
              AND NOT EXISTS (
                SELECT 1 FROM appointments a
                WHERE a.counselor_id = pc.id
                  AND a.status = 'confirmed'
                  AND a.appointment_datetime = ca.slot_start
              )
            """),
            {"now": now, "future_date": future_date}
        )
        
        slots = []
        for row in result.fetchall():
            from backend.core.security import decrypt_field
            
            counselor_id, encrypted_name, slot_start, slot_end, specialization = row
            slots.append(
                AvailabilitySlot(
                    counselor_id=counselor_id,
                    counselor_name=decrypt_field(encrypted_name),
                    slot_start=slot_start,
                    slot_end=slot_end,
                    specialization=specialization,
                )
            )
        
        logger.info(f"✓ Retrieved {len(slots)} available slots for student {current_user['profile_id']}")
        return slots
        
    except Exception as e:
        logger.error(f"✗ Error retrieving availability: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve availability"
        )


@router.post("/request", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def request_appointment(
    req: AppointmentRequest,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(consent_required),
):
    """
    Create an appointment request with a professional counselor.
    
    RULE-05: Urgency flag marks appointment for priority scheduling.
    RULE-07: Double-booking prevention via slot validation.
    
    Request Body:
    - counselor_id: Professional counselor UUID
    - requested_datetime: Desired appointment time
    - urgency_flag: (optional) Mark as urgent
    - reason_for_visit: (optional) Brief description
    
    Returns: Appointment details
    """
    if current_user["role"] != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can request appointments"
        )
    
    try:
        # Verify counselor exists
        counselor_result = await db.execute(
            select(ProfessionalCounselor).where(
                ProfessionalCounselor.id == uuid.UUID(req.counselor_id)
            )
        )
        counselor = counselor_result.scalar_one_or_none()
        
        if not counselor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Counselor not found"
            )
        
        # RULE-07: Check for double-booking
        is_available = await _check_double_booking(
            db,
            req.counselor_id,
            req.requested_datetime
        )
        
        if not is_available:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected time slot is not available"
            )
        
        # Create appointment (status: pending until counselor confirms)
        appointment = Appointment(
            id=uuid.uuid4(),
            student_id=uuid.UUID(current_user["profile_id"]),
            counselor_id=uuid.UUID(req.counselor_id),
            appointment_datetime=req.requested_datetime,
            status="pending",
            urgency_flag=req.urgency_flag,
            reason_for_visit=req.reason_for_visit,
            created_at=datetime.now(timezone.utc),
        )
        
        db.add(appointment)
        await db.commit()
        await db.refresh(appointment)
        
        logger.info(
            f"✓ Appointment created: {appointment.id} "
            f"(student: {current_user['profile_id']}, "
            f"counselor: {req.counselor_id}, "
            f"urgency: {req.urgency_flag})"
        )
        
        return AppointmentResponse.from_orm(appointment)
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid counselor ID format"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"✗ Error creating appointment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create appointment"
        )


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: str,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(consent_required),
):
    """Get appointment details (student or counselor only)."""
    try:
        appt_uuid = uuid.UUID(appointment_id)
        
        appointment_result = await db.execute(
            select(Appointment).where(Appointment.id == appt_uuid)
        )
        appointment = appointment_result.scalar_one_or_none()
        
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found"
            )
        
        # Verify access: student or counselor only
        is_student = (
            current_user["role"] == "student" and
            str(appointment.student_id) == current_user["profile_id"]
        )
        is_counselor = (
            current_user["role"] == "professional_counselor" and
            str(appointment.counselor_id) == current_user["profile_id"]
        )
        
        if not (is_student or is_counselor):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized to view this appointment"
            )
        
        return AppointmentResponse.from_orm(appointment)
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid appointment ID format"
        )


@router.patch("/{appointment_id}/confirm", response_model=AppointmentResponse)
async def confirm_appointment(
    appointment_id: str,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(consent_required),
):
    """
    Confirm appointment (counselor only).
    Transitions status from 'pending' → 'confirmed'.
    """
    if current_user["role"] != "professional_counselor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only counselors can confirm appointments"
        )
    
    try:
        appt_uuid = uuid.UUID(appointment_id)
        
        appointment_result = await db.execute(
            select(Appointment).where(Appointment.id == appt_uuid)
        )
        appointment = appointment_result.scalar_one_or_none()
        
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found"
            )
        
        if str(appointment.counselor_id) != current_user["profile_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the assigned counselor can confirm"
            )
        
        if appointment.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot confirm appointment with status '{appointment.status}'"
            )
        
        # Confirm appointment
        appointment.status = "confirmed"
        appointment.confirmed_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(appointment)
        
        logger.info(f"✓ Appointment confirmed: {appointment_id}")
        return AppointmentResponse.from_orm(appointment)
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid appointment ID format"
        )


@router.patch("/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: str,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(consent_required),
):
    """Cancel appointment (student or counselor)."""
    try:
        appt_uuid = uuid.UUID(appointment_id)
        
        appointment_result = await db.execute(
            select(Appointment).where(Appointment.id == appt_uuid)
        )
        appointment = appointment_result.scalar_one_or_none()
        
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found"
            )
        
        # Verify ownership
        is_student = (
            current_user["role"] == "student" and
            str(appointment.student_id) == current_user["profile_id"]
        )
        is_counselor = (
            current_user["role"] == "professional_counselor" and
            str(appointment.counselor_id) == current_user["profile_id"]
        )
        
        if not (is_student or is_counselor):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized to cancel this appointment"
            )
        
        if appointment.status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Appointment already cancelled"
            )
        
        appointment.status = "cancelled"
        await db.commit()
        
        logger.info(f"✓ Appointment cancelled: {appointment_id} by {current_user['role']}")
        return {"status": "cancelled", "message": "Appointment cancelled successfully"}
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid appointment ID format"
        )


@router.get("/my", response_model=list[AppointmentResponse])
async def get_my_appointments(
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(consent_required),
):
    """
    Get current user's appointments (student) or counselor's schedule (professional).
    
    Query Parameters:
    - status_filter: Filter by status (pending, confirmed, completed, cancelled)
    """
    try:
        query = select(Appointment)
        
        if current_user["role"] == "student":
            query = query.where(Appointment.student_id == uuid.UUID(current_user["profile_id"]))
        elif current_user["role"] == "professional_counselor":
            query = query.where(Appointment.counselor_id == uuid.UUID(current_user["profile_id"]))
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only students and counselors can view appointments"
            )
        
        if status_filter:
            query = query.where(Appointment.status == status_filter)
        
        # Order by appointment date, upcoming first
        query = query.order_by(Appointment.appointment_datetime.asc())
        
        result = await db.execute(query)
        appointments = result.scalars().all()
        
        logger.info(f"✓ Retrieved {len(appointments)} appointments for {current_user['role']}")
        return [AppointmentResponse.from_orm(a) for a in appointments]
        
    except Exception as e:
        logger.error(f"✗ Error retrieving appointments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve appointments"
        )
