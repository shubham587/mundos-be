from __future__ import annotations

from datetime import datetime
from enum import Enum

from typing import Optional

from .base import MongoModel, PyObjectId


class AppointmentStatus(str, Enum):
    booked = "booked"
    completed = "completed"
    cancelled = "cancelled"


class CreatedFrom(str, Enum):
    AI_AGENT_FORM = "AI_AGENT_FORM"
    MANUAL_ADMIN = "MANUAL_ADMIN"


class Appointment(MongoModel):
    patient_id: PyObjectId
    campaign_id: Optional[PyObjectId] = None
    appointment_date: datetime
    duration_minutes: int
    status: AppointmentStatus
    service_name: str
    notes: Optional[str] = None
    consulting_doctor: Optional[str] = None
    created_from: CreatedFrom

