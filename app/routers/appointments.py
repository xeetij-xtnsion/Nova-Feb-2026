from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.database import get_db
from app.models.appointment import Appointment

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/appointments")
async def list_appointments(db: AsyncSession = Depends(get_db)):
    """List all appointments (admin/verification endpoint)."""
    result = await db.execute(
        select(Appointment).order_by(Appointment.created_at.desc())
    )
    rows = result.scalars().all()

    return [
        {
            "id": a.id,
            "patient_name": a.patient_name,
            "phone": a.phone,
            "email": a.email,
            "service": a.service,
            "practitioner": a.practitioner,
            "appointment_date": str(a.appointment_date),
            "appointment_time": str(a.appointment_time),
            "status": a.status.value if a.status else None,
            "session_id": a.session_id,
            "notes": a.notes,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]
