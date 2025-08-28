from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .base import MongoModel, PyObjectId


class PatientType(str, Enum):
    EXISTING = "EXISTING"
    COLD_LEAD = "COLD_LEAD"


class ChannelType(str, Enum):
    email = "email"
    whatsapp = "whatsapp"
    sms = "sms"


class TreatmentHistoryItem(BaseModel):
    appointment_id: Optional[PyObjectId] = None
    procedure_name: Optional[str] = None
    procedure_date: Optional[datetime] = None
    next_recommended_follow_up: Optional[str] = None
    next_follow_up_date: Optional[datetime] = None


class Patient(MongoModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    name: str
    email: str
    phone: Optional[str] = None
    patient_type: PatientType
    preferred_channel: List[ChannelType] = Field(default_factory=list)
    treatment_history: Optional[List[TreatmentHistoryItem]] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None