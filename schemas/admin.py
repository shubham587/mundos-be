from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr
from models.campaign import (
    Campaign,
    CampaignType,
    CampaignStatus,
    Channel,
    FollowUpDetails,
    BookingFunnel,
)
from models.base import PyObjectId


class RecoveryCampaignCreate(BaseModel):
    patient_name: str
    patient_email: EmailStr
    initial_inquiry: Optional[str] = None
    estimated_value: Optional[float] = None


class CampaignRespondRequest(BaseModel):
    message: str
    new_status: str


class AdminAppointmentCreate(BaseModel):
    appointment_date: datetime
    duration_minutes: int
    name: str
    email: EmailStr
    phone: Optional[str] = None
    preferred_channel: Optional[str] = None
    service_name: str
    notes: Optional[str] = None
    consulting_doctor: Optional[str] = None


class CompleteAppointmentRequest(BaseModel):
    next_follow_up_date: Optional[datetime] = None
    next_recommended_follow_up: Optional[str] = None


class AppointmentReminderCampaignCreate(Campaign):
    # Allow nullable status for reminder campaigns while reusing Campaign fields
    patient_id: PyObjectId
    campaign_type: CampaignType = CampaignType.RECALL  # default will be overridden by caller
    status: Optional[CampaignStatus] = None
    channel: Optional[Channel] = None
    engagement_summary: Optional[str] = None
    follow_up_details: Optional[FollowUpDetails] = None
    booking_funnel: Optional[BookingFunnel] = None

