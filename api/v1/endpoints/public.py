from __future__ import annotations
import requests
from datetime import datetime, timezone, timedelta, time
import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv, find_dotenv

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.database import get_database
from core.config import settings
from repositories.base import BaseRepository
from models.appointment import Appointment, AppointmentStatus, CreatedFrom
from models.campaign import CampaignStatus
from schemas.public import AppointmentBookingRequest, AppointmentBookingResponse


router = APIRouter(tags=["public"])

load_dotenv(find_dotenv(), override=True)


@router.get("/availability")
async def get_availability(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000),
    date: str | None = None,
) -> dict[str, list[str]]:
    # Generated schedule: Sun–Sat, 09:00–20:30 every 30 minutes.
    # Removes any slots already booked in the appointments collection.
    from calendar import monthrange

    db = await get_database()
    repo = BaseRepository(db)

    # Resolve clinic timezone for slot calculation (defaults to UTC)
    tz_name = os.getenv("TZ", "UTC")
    try:
        clinic_tz = ZoneInfo(tz_name)
    except Exception:
        clinic_tz = ZoneInfo("UTC")

    # Helper to generate base half-hour slots 09:00–20:30
    def _generate_base_slots() -> list[str]:
        base: list[str] = []
        for hour in range(9, 21):  # 9 to 20 inclusive => 20:30 last half-hour
            for minute in (0, 30):
                base.append(f"{hour:02d}:{minute:02d}")
        return base

    # Remove all half-hour slots that overlap with [start_local, start_local+duration)
    def _remove_occupied(
        available: set[str], *,
        day_local: datetime.date, start_local: datetime, duration_minutes: int
    ) -> None:
        try:
            dur = int(duration_minutes)
        except Exception:
            dur = 45
        if dur <= 0:
            dur = 45
        end_local = start_local + timedelta(minutes=dur)
        tzinfo = start_local.tzinfo
        # Iterate over existing labels and drop those that fall within the occupied interval
        labels = list(available)
        for label in labels:
            try:
                hh, mm = label.split(":")
                slot_dt = datetime(day_local.year, day_local.month, day_local.day, int(hh), int(mm))
                if tzinfo is not None:
                    slot_dt = slot_dt.replace(tzinfo=tzinfo)
                # Start-inclusive, end-exclusive
                if start_local <= slot_dt < end_local:
                    available.discard(label)
            except Exception:
                # Ignore malformed labels
                continue

    # If a specific date is provided (YYYY-MM-DD), return availability for that date only
    if date:
        try:
            # Expect ISO date like 2025-08-12
            target_dt = datetime.fromisoformat(date).date()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        base_slots = _generate_base_slots()
        available = set(base_slots)

        # Compute local day start/end and convert to UTC naive for range query (works with typical Mongo UTC-naive storage)
        start_local = datetime.combine(target_dt, time.min, tzinfo=clinic_tz)
        end_local = datetime.combine(target_dt, time.max, tzinfo=clinic_tz)
        start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
        end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
        day_filter = {"appointment_date": {"$gte": start_utc, "$lte": end_utc}}

        # Fetch only relevant appointments (date + optional service)
        day_appts = await repo.find_many("appointments", day_filter)
        for a in day_appts:
            ts = a.get("appointment_date")
            if isinstance(ts, datetime):
                # Normalize to UTC if naive, then convert to local time before comparing to generated local schedule
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                local_ts = ts.astimezone(clinic_tz)
                if local_ts.date() == target_dt:
                    _remove_occupied(available, day_local=target_dt, start_local=local_ts, duration_minutes=a.get("duration_minutes", 45))

        return {target_dt.isoformat(): sorted(available)}

    num_days = monthrange(year, month)[1]
    base_slots: list[str] = _generate_base_slots()

    slots_by_date: dict[str, list[str]] = {}
    # Pre-fetch appointments for the month (range + optional service)
    start_of_month_local = datetime(year, month, 1, 0, 0, 0, tzinfo=clinic_tz)
    end_of_month_local = datetime(year, month, num_days, 23, 59, 59, 999999, tzinfo=clinic_tz)
    start_of_month_utc = start_of_month_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_of_month_utc = end_of_month_local.astimezone(timezone.utc).replace(tzinfo=None)
    month_filter = {"appointment_date": {"$gte": start_of_month_utc, "$lte": end_of_month_utc}}
    month_appts = await repo.find_many("appointments", month_filter)
    for day in range(1, num_days + 1):
        dt = datetime(year, month, day)
        # Allow all days
        date_str = dt.date().isoformat()
        available = set(base_slots)

        # Remove booked appointment slots for this date by parsing stored values
        for a in month_appts:
            ts = a.get("appointment_date")
            if isinstance(ts, datetime):
                # Normalize to UTC if naive, then convert to local time before comparing to generated local schedule
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                local_ts = ts.astimezone(clinic_tz)
                if local_ts.date() == dt.date():
                    _remove_occupied(available, day_local=dt.date(), start_local=local_ts, duration_minutes=a.get("duration_minutes", 45))

        slots_by_date[date_str] = sorted(available)

    return slots_by_date


class PhoneBookingRequest(BaseModel):
    number: str
    name: str


@router.get("/phone_booking_post")
async def phone_booking_post(number: str, name: str):
    # Placeholder: the booking link base is available via BOOKING_BASE_URL env var
    # Implement logic here

    print(f"{number=}")
    print(f"{name=}")
    # Clean phone number format by replacing space with + if needed
    if number.startswith(" "):
        number = "+" + number[1:]
        print(f"Formatted number: {number}")  
    account_sid = settings.twilio_account_sid or "AC818b92cb650c02505d1d1e473c3b33c2"
    auth_token = settings.twilio_auth_token or "deb3010e2119bffa41d091f3d2bc2705"

    print(f"{account_sid=}")
    print(f"{auth_token=}")
    url = f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json'
    # Message data
    data = {
        'To': number,
        'From': (settings.twilio_phone_number or "+16084133165"),
        'Body': f'''
            Hi {name},
            It was a pleasure speaking with you. Here is the booking link as we discussed. You can select a convenient time slot as per your availability-
            {settings.booking_base_url}
            For any further enquiries, feel free to reach out to us at +55 (11) 4567-8910.
            Best,
            Bright Smile Clinic Team
        '''
    }
    # Send POST request
    try:
        response = requests.post(url, data=data, auth=(account_sid, auth_token))
        return {"message": "Message sent successfully"}, 200
    except Exception as e:
        return {"message": f"Error sending message: {str(e)}"}, 400



@router.post("/appointments/book", response_model=AppointmentBookingResponse)
async def book_appointment(payload: AppointmentBookingRequest) -> AppointmentBookingResponse:
    db = await get_database()
    repo = BaseRepository(db)

    # Step 1: Identify the patient strictly by email (per requirement)
    patient = await repo.find_one("patients", {"email": payload.email})
    if not patient:
        # Return a generic message suitable for public UX
        raise HTTPException(status_code=404, detail="User not found")

    # Step 1c: Find most recent active BOOKING_INITIATED campaign
    # Use repository to emulate a sorted find_one
    campaigns = await repo.find_many(
        "campaigns",
        {
            "status": CampaignStatus.BOOKING_INITIATED.value,
            "$or": [
                {"patient_id": patient["_id"]},
                {"patient_id": str(patient["_id"])},
            ],
        },
        sort=[("updated_at", -1)],
        limit=1,
    )
    campaign = campaigns[0] if campaigns else None
    if not campaign:
        # Hide internal campaign-state details from public forms
        raise HTTPException(status_code=404, detail="User not found")

    # Step 2: Create the appointment document
    appointment_doc = Appointment(
        patient_id=patient["_id"],  # type: ignore[arg-type]
        campaign_id=campaign["_id"],  # type: ignore[arg-type]
        appointment_date=payload.appointment_date,
        duration_minutes=payload.duration_minutes or 30,
        status=AppointmentStatus.booked,
        service_name=payload.service_name,
        notes=None,
        created_from=CreatedFrom.AI_AGENT_FORM,
    ).model_dump(by_alias=True, exclude_none=False)

    inserted_id = await repo.insert_one("appointments", appointment_doc)

    # Step 3: Update campaign status to BOOKING_COMPLETED
    await repo.update_one("campaigns", {"_id": campaign["_id"]}, {"$set": {"status": CampaignStatus.BOOKING_COMPLETED.value}})

    return AppointmentBookingResponse(message="Appointment booked successfully.", appointment_id=str(inserted_id))


