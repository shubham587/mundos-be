from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List

from bson import ObjectId
from pydantic import BaseModel, Field, ConfigDict


class CampaignType(str, Enum):
    ATTEMPTING_RECOVERY = "ATTEMPTING_RECOVERY"
    RECOVERY = "RECOVERY"
    RECALL = "RECALL"


class CampaignStatus(str, Enum):
    ATTEMPTING_RECOVERY = "ATTEMPTING_RECOVERY"
    RE_ENGAGED = "RE_ENGAGED"
    HANDOFF_REQUIRED = "HANDOFF_REQUIRED"
    RECOVERED = "RECOVERED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    RECOVERY_DECLINED = "RECOVERY_DECLINED"
    BOOKING_COMPLETED = "BOOKING_COMPLETED"
    QUEUED = "QUEUED"


class BookingFunnelStatus(str, Enum):
    FORM_SENT = "FORM_SENT"
    FORM_SUBMITTED = "FORM_SUBMITTED"

class MongoModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)


class FollowUpDetails(MongoModel):
    attempts_made: int
    max_attempts: int
    next_attempt_at: datetime


class Channel(MongoModel):
    type: str
    thread_id: Optional[str] = None

class BookingFunnel(MongoModel):
    status: Optional[BookingFunnelStatus] = None
    link_url: Optional[str] = None
    submitted_at: Optional[datetime] = None

class Campaign(MongoModel):
    id: Optional[ObjectId] = Field(default=None, alias="_id")
    patient_id: ObjectId
    campaign_type: CampaignType
    service_name: str
    status: CampaignStatus
    channel: Optional[Channel] = None
    booking_funnel: Optional[BookingFunnel] = None
    engagement_summary: Optional[str] = None
    follow_up_details: FollowUpDetails
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class PatientType(str, Enum):
    EXISTING = "EXISTING"
    COLD_LEAD = "COLD_LEAD"

class TreatmentHistory(MongoModel):
    procedure_name: Optional[str] = None
    procedure_date: Optional[datetime] = None
    next_recommended_follow_up: Optional[str] = None
    next_follow_up_date: Optional[datetime] = None
    appointment_id: Optional[ObjectId] = None

class Patient(MongoModel):
    id: Optional[ObjectId] = Field(default=None, alias="_id")
    name: str
    email: str
    phone: Optional[str] = None
    patient_type: PatientType
    preferred_channel: Optional[List[str]] = None
    treatment_history: Optional[List[TreatmentHistory]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Interaction(MongoModel):
    id: Optional[ObjectId] = Field(default=None, alias="_id")
    campaign_id: ObjectId
    direction: InteractionDirection
    content: str
    ai_analysis: Optional[AiAnalysis] = None
    timestamp: datetime

class InteractionDirection(str, Enum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"

class AiAnalysis(MongoModel):
    intent: Optional[str] = None
    sentiment: Optional[str] = None


