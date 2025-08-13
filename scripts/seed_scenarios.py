from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from zoneinfo import ZoneInfo

from core.config import settings


UTC = timezone.utc


def _clinic_tz() -> ZoneInfo:
    tz_name = os.getenv("TZ", "UTC")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def to_utc_naive_from_local(local_dt: datetime) -> datetime:
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=_clinic_tz())
    return local_dt.astimezone(UTC).replace(tzinfo=None)


async def pick_patients(db: AsyncIOMotorDatabase, needed: int = 2) -> list[dict[str, Any]]:
    pts: list[dict[str, Any]] = []
    async for p in db["patients"].find({}).limit(needed):
        pts.append(p)
    # Create missing patients (EXISTING) if fewer than needed
    to_create = max(0, needed - len(pts))
    seed_defs = [
        {"name": "Alice Johnson", "email": "alice@example.com", "phone": "+1-202-555-0111", "patient_type": "EXISTING", "preferred_channel": ["email", "sms"]},
        {"name": "Bob Lee", "email": "bob@example.com", "phone": "+1-202-555-0122", "patient_type": "EXISTING", "preferred_channel": ["email"]},
    ]
    for i in range(to_create):
        seed = seed_defs[i]
        existing = await db["patients"].find_one({"email": seed["email"]})
        if existing:
            pts.append(existing)
            continue
        now = datetime.now(UTC)
        doc = {**seed, "created_at": now, "updated_at": now}
        res = await db["patients"].insert_one(doc)
        new_doc = {**doc, "_id": res.inserted_id}
        pts.append(new_doc)
    return pts[:needed]


async def create_campaign(
    db: AsyncIOMotorDatabase,
    *,
    patient_id: Any,
    campaign_type: str,
    status: str,
    channel_type: Optional[str] = None,
    attempts_made: int = 0,
    max_attempts: int = 3,
    next_attempt_at: Optional[datetime] = None,
    engagement_summary: Optional[str] = None,
    booking_status: Optional[str] = None,
    booking_link: Optional[str] = None,
    service_name: Optional[str] = None,
) -> Any:
    doc: dict[str, Any] = {
        "patient_id": patient_id,
        "campaign_type": campaign_type,
        "status": status,
        "follow_up_details": {
            "attempts_made": attempts_made,
            "max_attempts": max_attempts,
            "next_attempt_at": next_attempt_at,
        },
        "engagement_summary": engagement_summary,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    if channel_type:
        doc["channel"] = {"type": channel_type}
    if booking_status or booking_link:
        doc["booking_funnel"] = {
            "status": booking_status,
            "link_url": booking_link,
            "submitted_at": None,
        }
    if service_name:
        doc["service_name"] = service_name
    res = await db["campaigns"].insert_one(doc)
    return res.inserted_id


async def add_interaction(
    db: AsyncIOMotorDatabase,
    *,
    campaign_id: Any,
    direction: str,
    content: str,
    minutes_ago: int = 0,
) -> None:
    ts = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    await db["interactions"].insert_one(
        {
            "campaign_id": campaign_id,
            "direction": direction,
            "content": content,
            "timestamp": ts,
            "created_at": ts,
            "updated_at": ts,
        }
    )


async def add_appointment(
    db: AsyncIOMotorDatabase,
    *,
    patient_id: Any,
    campaign_id: Optional[Any],
    local_dt: datetime,
    duration_minutes: int,
    service_name: str,
    consulting_doctor: Optional[str] = None,
    created_from: str = "AI_AGENT_FORM",
) -> Any:
    dt_utc_naive = to_utc_naive_from_local(local_dt)
    doc: dict[str, Any] = {
        "patient_id": patient_id,
        "campaign_id": campaign_id,
        "appointment_date": dt_utc_naive,
        "duration_minutes": duration_minutes,
        "status": "booked",
        "service_name": service_name,
        "consulting_doctor": consulting_doctor,
        "created_from": created_from,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    res = await db["appointments"].insert_one(doc)
    return res.inserted_id


async def main() -> None:
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.database_name]
    try:
        patients = await pick_patients(db, needed=2)
        p1, p2 = patients[0], patients[1]

        # Scenario A: Recovery via SMS (routes to call_patient node)
        c_recovery_sms = await create_campaign(
            db,
            patient_id=p1["_id"],
            campaign_type="RECOVERY",
            status="ATTEMPTING_RECOVERY",
            channel_type="sms",
            attempts_made=0,
            next_attempt_at=datetime.now(UTC),
            service_name="Dental Implants",
        )
        await add_interaction(
            db,
            campaign_id=c_recovery_sms,
            direction="outgoing",
            content="Initial SMS outreach created by seed",
            minutes_ago=30,
        )

        # Scenario B: Recovery re-engaged via Email
        c_recovery_email = await create_campaign(
            db,
            patient_id=p2["_id"],
            campaign_type="RECOVERY",
            status="RE_ENGAGED",
            channel_type="email",
            attempts_made=1,
            next_attempt_at=datetime.now(UTC),
            engagement_summary="Patient replied positively.",
            service_name="Routine Checkup",
        )
        await add_interaction(db, campaign_id=c_recovery_email, direction="outgoing", content="Outreach email #1", minutes_ago=180)
        await add_interaction(db, campaign_id=c_recovery_email, direction="incoming", content="Sounds good, what's next?", minutes_ago=175)

        # Scenario C: Recall campaign
        c_recall = await create_campaign(
            db,
            patient_id=p2["_id"],
            campaign_type="RECALL",
            status="ATTEMPTING_RECOVERY",
            channel_type="email",
            attempts_made=2,
            max_attempts=3,
            next_attempt_at=datetime.now(UTC),
            service_name="Teeth Cleaning",
        )

        # Scenario D: Booking initiated (so public booking flow can find it)
        c_booking = await create_campaign(
            db,
            patient_id=p1["_id"],
            campaign_type="RECOVERY",
            status="BOOKING_INITIATED",
            channel_type="email",
            booking_status="FORM_SENT",
            booking_link=(settings.booking_base_url or "https://booking.example.com") + "/form/TEST-123",
            attempts_made=0,
            next_attempt_at=datetime.now(UTC),
            service_name="Dental Implants",
        )

        # Scenario E: An appointment on a target date to test availability
        # Next business day 15:00 local, 30 minutes
        target_local = datetime.now(_clinic_tz()).replace(hour=15, minute=0, second=0, microsecond=0)
        if target_local < datetime.now(_clinic_tz()):
            target_local = target_local + timedelta(days=1)
        appt_id = await add_appointment(
            db,
            patient_id=p1["_id"],
            campaign_id=c_booking,
            local_dt=target_local,
            duration_minutes=30,
            service_name="Dental Implants",
            consulting_doctor="Dr. Johnson",
        )

        print("Seed complete:")
        print(
            {
                "recovery_sms_campaign": str(c_recovery_sms),
                "recovery_email_campaign": str(c_recovery_email),
                "recall_campaign": str(c_recall),
                "booking_initiated_campaign": str(c_booking),
                "appointment_id": str(appt_id),
            }
        )
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())


