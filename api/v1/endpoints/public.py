from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from db.database import get_database
from repositories.base import BaseRepository
from models.appointment import Appointment, AppointmentStatus, CreatedFrom
from models.campaign import CampaignStatus
from schemas.public import AppointmentBookingRequest, AppointmentBookingResponse


router = APIRouter(tags=["public"])


@router.get("/availability")
async def get_availability(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000),
    service_id: str | None = None,
) -> dict[str, list[str]]:
    # Generated schedule: Sun–Sat, 09:00–20:30 every 30 minutes.
    # Removes any slots already booked in the appointments collection.
    from calendar import monthrange

    db = await get_database()
    repo = BaseRepository(db)

    num_days = monthrange(year, month)[1]
    base_slots: list[str] = []
    for hour in range(9, 21):  # 9 to 20 inclusive => 20:30 last half-hour
        for minute in (0, 30):
            base_slots.append(f"{hour:02d}:{minute:02d}")

    slots_by_date: dict[str, list[str]] = {}
    # Pre-fetch appointments for the month and filter in Python to avoid type
    # inconsistencies if timestamps are stored as strings
    month_appts = await repo.find_many("appointments", {})
    for day in range(1, num_days + 1):
        dt = datetime(year, month, day)
        # Allow all days
        date_str = dt.date().isoformat()
        available = set(base_slots)

        # Remove booked appointment slots for this date by parsing stored values
        for a in month_appts:
            ts = a.get("appointment_date")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    ts = None
            if isinstance(ts, datetime):
                # Normalize to UTC if naive, then convert to local time before comparing to generated local schedule
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                local_ts = ts.astimezone()  # system local timezone
                if local_ts.date() == dt.date():
                    available.discard(local_ts.strftime("%H:%M"))

        slots_by_date[date_str] = sorted(available)

    return slots_by_date


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
        duration_minutes=payload.duration_minutes or 45,
        status=AppointmentStatus.booked,
        service_name=payload.service_name,
        notes=None,
        created_from=CreatedFrom.AI_AGENT_FORM,
    ).model_dump(by_alias=True, exclude_none=False)

    inserted_id = await repo.insert_one("appointments", appointment_doc)

    # Step 3: Update campaign status to BOOKING_COMPLETED
    await repo.update_one("campaigns", {"_id": campaign["_id"]}, {"$set": {"status": CampaignStatus.BOOKING_COMPLETED.value}})

    return AppointmentBookingResponse(message="Appointment booked successfully.", appointment_id=str(inserted_id))


