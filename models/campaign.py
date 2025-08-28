from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from .base import MongoModel, PyObjectId


class CampaignType(str, Enum):
    RECALL = "RECALL"
    RECOVERY = "RECOVERY"
    APPOINTMENT_REMINDER = "APPOINTMENT_REMINDER"


class CampaignStatus(str, Enum):
    ATTEMPTING_RECOVERY = "ATTEMPTING_RECOVERY"
    RE_ENGAGED = "RE_ENGAGED"
    HANDOFF_REQUIRED = "HANDOFF_REQUIRED"
    RECOVERED = "RECOVERED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    BOOKING_INITIATED = "BOOKING_INITIATED"
    RECOVERY_DECLINED = "RECOVERY_DECLINED"
    BOOKING_COMPLETED = "BOOKING_COMPLETED"
    QUEUED = "QUEUED" 


class BookingFunnelStatus(str, Enum):
    FORM_SENT = "FORM_SENT"
    FORM_SUBMITTED = "FORM_SUBMITTED"


class Channel(BaseModel):
    type: str
    thread_id: Optional[str] = None


class FollowUpDetails(BaseModel):
    attempts_made: int = 0
    max_attempts: int = 3
    next_attempt_at: Optional[datetime] = None


class BookingFunnel(BaseModel):
    status: Optional[BookingFunnelStatus] = None
    link_url: Optional[str] = None
    submitted_at: Optional[datetime] = None


class Campaign(MongoModel):
    patient_id: PyObjectId
    campaign_type: CampaignType
    service_name: str
    status: CampaignStatus
    channel: Optional[Channel] = None
    engagement_summary: Optional[str] = None
    follow_up_details: Optional[FollowUpDetails] = None
    booking_funnel: Optional[BookingFunnel] = None