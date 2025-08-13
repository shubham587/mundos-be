from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient


def get_db():
    load_dotenv()
    client = MongoClient(os.getenv("MONGO_URI", "mongodb+srv://algoholics06:Algoholics06@cluster0.iuxnwdd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"))
    return client[os.getenv("MONGO_DB_NAME", "AI-lead-recovery")]


def upsert_patient(db, email: str, now: datetime) -> ObjectId:
    existing = db.patients.find_one({"email": email})
    if existing:
        return existing["_id"]
    doc = {
        "name": "Henish",
        "email": email,
        "phone": None,
        "patient_type": "COLD_LEAD",
        "preferred_channel": None,
        "treatment_history": None,
        "created_at": now,
        "updated_at": now,
    }
    return db.patients.insert_one(doc).inserted_id


def full_campaign(
    patient_id: ObjectId,
    *,
    campaign_type: str,
    status: str,
    service_name: str,
    attempts_made: int,
    max_attempts: int,
    next_at: datetime,
    booking_status: str | None = None,
    engagement_summary: str | None = None,
    now: datetime,
) -> Dict[str, Any]:
    return {
        "patient_id": patient_id,
        "campaign_type": campaign_type,
        "service_name": service_name,
        "status": status,
        "channel": {"type": "email", "thread_id": None},
        "engagement_summary": engagement_summary,
        "follow_up_details": {
            "attempts_made": attempts_made,
            "max_attempts": max_attempts,
            "next_attempt_at": next_at,
        },
        "booking_funnel": {
            "status": booking_status,
            "link_url": None,
            "submitted_at": None,
        },
        "created_at": now,
        "updated_at": now,
    }


def insert_interaction(db, campaign_id: ObjectId, *, direction: str, content: str, ts: datetime) -> ObjectId:
    doc = {
        "campaign_id": campaign_id,
        "direction": direction,  # 'incoming' or 'outgoing'
        "content": content,
        "ai_analysis": {"intent": None, "sentiment": None},
        "timestamp": ts,
    }
    return db.interactions.insert_one(doc).inserted_id


def main() -> None:
    db = get_db()
    now = datetime.utcnow()
    due = now - timedelta(minutes=5)
    future = now + timedelta(days=2)

    email = os.getenv("TEST_SEED_EMAIL", "henishshah2820@gmail.com")
    patient_id = upsert_patient(db, email, now)

    ids: Dict[str, ObjectId] = {}
    appt_ids: Dict[str, ObjectId] = {}

    # 1) Recovery: due, first attempt (no interactions)
    c1 = full_campaign(
        patient_id,
        campaign_type="RECOVERY",
        status="ATTEMPTING_RECOVERY",
        service_name="dental_implants",
        attempts_made=0,
        max_attempts=3,
        next_at=due,
        booking_status=None,
        engagement_summary=None,
        now=now,
    )
    ids["recovery_first_due"] = db.campaigns.insert_one(c1).inserted_id

    # 2) Recovery: due, penultimate attempt with interactions (attempts=2/3)
    c2 = full_campaign(
        patient_id,
        campaign_type="RECOVERY",
        status="ATTEMPTING_RECOVERY",
        service_name="Dental crowns",
        attempts_made=2,
        max_attempts=3,
        next_at=due,
        booking_status=None,
        engagement_summary=None,
        now=now,
    )
    ids["recovery_penultimate_due"] = db.campaigns.insert_one(c2).inserted_id
    insert_interaction(db, ids["recovery_penultimate_due"], direction="incoming", content="Hi, I wanted to know pricing.", ts=now - timedelta(days=2))
    insert_interaction(db, ids["recovery_penultimate_due"], direction="outgoing", content="Thanks for reaching out! Happy to help.", ts=now - timedelta(days=2, hours=23))
    insert_interaction(db, ids["recovery_penultimate_due"], direction="incoming", content="Great, please share next steps.", ts=now - timedelta(days=1, hours=20))

    # 3) Recovery: recovered (skip)
    c3 = full_campaign(
        patient_id,
        campaign_type="RECOVERY",
        status="RECOVERED",
        service_name="Veneers",
        attempts_made=1,
        max_attempts=3,
        next_at=due,
        booking_status=None,
        engagement_summary=None,
        now=now,
    )
    ids["recovery_recovered"] = db.campaigns.insert_one(c3).inserted_id
    # prior interactions (for realism; agent should still skip)
    insert_interaction(db, ids["recovery_recovered"], direction="outgoing", content="Thanks, your appointment is confirmed.", ts=now - timedelta(days=1))

    # 4) Recovery: booking form submitted (skip)
    c4 = full_campaign(
        patient_id,
        campaign_type="RECOVERY",
        status="ATTEMPTING_RECOVERY",
        service_name="Teeth whitening",
        attempts_made=1,
        max_attempts=3,
        next_at=due,
        booking_status="FORM_SUBMITTED",
        engagement_summary=None,
        now=now,
    )
    ids["recovery_form_submitted"] = db.campaigns.insert_one(c4).inserted_id
    # prior interaction indicating form was submitted
    insert_interaction(db, ids["recovery_form_submitted"], direction="incoming", content="I have submitted the form.", ts=now - timedelta(hours=12))

    # 5) Recall: due, first attempt (no booking link, at least 1 incoming interaction)
    c5 = full_campaign(
        patient_id,
        campaign_type="RECALL",
        status="ATTEMPTING_RECOVERY",
        service_name="Routine dental work",
        attempts_made=0,
        max_attempts=3,
        next_at=due,
        booking_status=None,
        engagement_summary=None,
        now=now,
    )
    ids["recall_first_due"] = db.campaigns.insert_one(c5).inserted_id
    insert_interaction(db, ids["recall_first_due"], direction="incoming", content="Is it time for my recall visit?", ts=now - timedelta(days=3))

    # 6) Recall: not due (time gate)
    c6 = full_campaign(
        patient_id,
        campaign_type="RECALL",
        status="ATTEMPTING_RECOVERY",
        service_name="Routine dental work",
        attempts_made=0,
        max_attempts=3,
        next_at=future,
        booking_status=None,
        engagement_summary=None,
        now=now,
    )
    ids["recall_not_due"] = db.campaigns.insert_one(c6).inserted_id

    # 7) Appointment reminder: due, first and only
    c7 = full_campaign(
        patient_id,
        campaign_type="APPOINTMENT_REMINDER",
        status="ATTEMPTING_RECOVERY",
        service_name="Routine dental work",
        attempts_made=0,
        max_attempts=1,
        next_at=due,
        booking_status=None,
        engagement_summary=None,
        now=now,
    )
    ids["appt_due_first"] = db.campaigns.insert_one(c7).inserted_id
    # prior incoming about scheduling
    insert_interaction(db, ids["appt_due_first"], direction="incoming", content="Can I confirm the timing for tomorrow?", ts=now - timedelta(hours=2))
    # create appointment for the reminder campaign (appointment is tomorrow 10:00 UTC)
    appointment_date = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    appt_doc = {
        "patient_id": patient_id,
        "campaign_id": ids["appt_due_first"],
        "appointment_date": appointment_date,
        "duration_minutes": 30,
        "status": "booked",
        "service_name": "Routine dental work",
        "notes": "Seeded test appointment",
        "consulting_doctor": "Dr. Smith",
        "created_from": "MANUAL_ADMIN",
        "created_at": now,
        "updated_at": now,
    }
    appt_ids["appt_due_first"] = db.appointments.insert_one(appt_doc).inserted_id

    # 8) Appointment reminder: already sent (skip)
    c8 = full_campaign(
        patient_id,
        campaign_type="APPOINTMENT_REMINDER",
        status="ATTEMPTING_RECOVERY",
        service_name="Routine dental work",
        attempts_made=1,
        max_attempts=1,
        next_at=due,
        booking_status=None,
        engagement_summary=None,
        now=now,
    )
    ids["appt_already_sent"] = db.campaigns.insert_one(c8).inserted_id
    # previous reminder already logged
    insert_interaction(db, ids["appt_already_sent"], direction="outgoing", content="Reminder: your appointment is tomorrow.", ts=now - timedelta(days=1))
    # appointment also exists for the already-sent reminder
    appointment_date2 = (now + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
    appt_doc2 = {
        "patient_id": patient_id,
        "campaign_id": ids["appt_already_sent"],
        "appointment_date": appointment_date2,
        "duration_minutes": 45,
        "status": "booked",
        "service_name": "Routine dental work",
        "notes": "Seeded test appointment (already reminded)",
        "consulting_doctor": "Dr. Lee",
        "created_from": "MANUAL_ADMIN",
        "created_at": now,
        "updated_at": now,
    }
    appt_ids["appt_already_sent"] = db.appointments.insert_one(appt_doc2).inserted_id

    # 9) Recovery: due, first attempt with prior AI summary present (no interactions)
    pre_summary = (
        "Overall Summary-\nPrior discussion suggested interest in dental implants.\n\n"
        "Chatwise Summary-\n\n2025-01-01T10:00:00Z: Patient asked about cost.\n"
    )
    c9 = full_campaign(
        patient_id,
        campaign_type="RECOVERY",
        status="ATTEMPTING_RECOVERY",
        service_name="dental_implants",
        attempts_made=0,
        max_attempts=3,
        next_at=due,
        booking_status=None,
        engagement_summary=pre_summary,
        now=now,
    )
    ids["recovery_first_due_with_summary"] = db.campaigns.insert_one(c9).inserted_id

    print({k: str(v) for k, v in ids.items()})
    print({f"appointment_{k}": str(v) for k, v in appt_ids.items()})


if __name__ == "__main__":
    main()


