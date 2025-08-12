from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class AppointmentBookingRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str
    appointment_date: datetime
    service_name: str
    duration_minutes: Optional[int] = 30


class AppointmentBookingResponse(BaseModel):
    message: str
    appointment_id: str

