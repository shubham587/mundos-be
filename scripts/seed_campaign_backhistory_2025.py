from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict

from dotenv import load_dotenv
from pymongo import MongoClient


def get_db():
    load_dotenv()
    client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    return client[os.getenv("MONGO_DB_NAME", "AI-lead-recovery")]


def upsert_existing_patient(db, *, name: str, email: str, phone: str) -> Any:
    existing = db.patients.find_one({"email": email})
    if existing:
        return existing["_id"]
    now = datetime(2025, 6, 1, 10, 0, 0)
    doc = {
        "name": name,
        "email": email,
        "phone": phone,
        "patient_type": "EXISTING",
        "preferred_channel": ["email", "sms"],
        "treatment_history": [],
        "created_at": now,
        "updated_at": now,
    }
    return db.patients.insert_one(doc).inserted_id


def campaign_doc(
    *,
    patient_id: Any,
    campaign_type: str,
    status: str,
    service_name: str,
    attempts_made: int,
    max_attempts: int,
    next_attempt_at: datetime,
    created_at: datetime,
    engagement_summary: str | None = None,
) -> Dict[str, Any]:
    # Strictly match the structure used in scripts/seed_full_flow_test.py
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
            "next_attempt_at": next_attempt_at,
        },
        "booking_funnel": {
            "status": None,
            "link_url": None,
            "submitted_at": None,
        },
        "created_at": created_at,
        "updated_at": created_at,
    }


def main() -> None:
    db = get_db()

    # Guaranteed 2025 dates (all before Aug 1, 2025 for next_attempt_at)
    june10 = datetime(2025, 6, 10, 9, 0, 0)
    june20 = datetime(2025, 6, 20, 9, 0, 0)
    july5 = datetime(2025, 7, 5, 9, 0, 0)
    july12 = datetime(2025, 7, 12, 9, 0, 0)
    july20 = datetime(2025, 7, 20, 9, 0, 0)

    # Patients (EXISTING) used as foreign keys in campaigns
    p1 = upsert_existing_patient(db, name="Alice Backhistory", email="alice.backhistory@example.com", phone="+1-202-555-1111")
    p2 = upsert_existing_patient(db, name="Bob Backhistory", email="bob.backhistory@example.com", phone="+1-202-555-2222")

    ids: Dict[str, Any] = {}

    # Recovery campaigns (4 statuses)
    ids["recovery_recovered"] = db.campaigns.insert_one(
        campaign_doc(
            patient_id=p1,
            campaign_type="RECOVERY",
            status="RECOVERED",
            service_name="Dental Implants",
            attempts_made=2,
            max_attempts=3,
            next_attempt_at=july5,
            created_at=june10,
            engagement_summary="Recovered after scheduling confirmation.",
        )
    ).inserted_id

    ids["recovery_failed"] = db.campaigns.insert_one(
        campaign_doc(
            patient_id=p1,
            campaign_type="RECOVERY",
            status="RECOVERY_FAILED",
            service_name="Root Canal",
            attempts_made=3,
            max_attempts=3,
            next_attempt_at=july12,
            created_at=june10,
            engagement_summary="No response after multiple attempts.",
        )
    ).inserted_id

    ids["recovery_declined"] = db.campaigns.insert_one(
        campaign_doc(
            patient_id=p2,
            campaign_type="RECOVERY",
            status="RECOVERY_DECLINED",
            service_name="Teeth Whitening",
            attempts_made=1,
            max_attempts=3,
            next_attempt_at=june20,
            created_at=june10,
            engagement_summary="Patient declined service politely.",
        )
    ).inserted_id

    ids["recovery_handoff"] = db.campaigns.insert_one(
        campaign_doc(
            patient_id=p2,
            campaign_type="RECOVERY",
            status="HANDOFF_REQUIRED",
            service_name="Braces Consultation",
            attempts_made=1,
            max_attempts=3,
            next_attempt_at=july20,
            created_at=june10,
            engagement_summary="Complex insurance question; human follow-up needed.",
        )
    ).inserted_id

    # Recall campaigns (4 statuses)
    ids["recall_recovered"] = db.campaigns.insert_one(
        campaign_doc(
            patient_id=p1,
            campaign_type="RECALL",
            status="RECOVERED",
            service_name="Routine Cleaning",
            attempts_made=1,
            max_attempts=3,
            next_attempt_at=july12,
            created_at=june10,
            engagement_summary="Recall completed successfully.",
        )
    ).inserted_id

    ids["recall_failed"] = db.campaigns.insert_one(
        campaign_doc(
            patient_id=p2,
            campaign_type="RECALL",
            status="RECOVERY_FAILED",
            service_name="Routine Exam",
            attempts_made=3,
            max_attempts=3,
            next_attempt_at=july20,
            created_at=june10,
            engagement_summary="Recall attempts exhausted.",
        )
    ).inserted_id

    ids["recall_declined"] = db.campaigns.insert_one(
        campaign_doc(
            patient_id=p1,
            campaign_type="RECALL",
            status="RECOVERY_DECLINED",
            service_name="Fluoride Treatment",
            attempts_made=1,
            max_attempts=3,
            next_attempt_at=june20,
            created_at=june10,
            engagement_summary="Patient opted to skip recall this time.",
        )
    ).inserted_id

    ids["recall_handoff"] = db.campaigns.insert_one(
        campaign_doc(
            patient_id=p2,
            campaign_type="RECALL",
            status="HANDOFF_REQUIRED",
            service_name="Deep Cleaning",
            attempts_made=2,
            max_attempts=3,
            next_attempt_at=july5,
            created_at=june10,
            engagement_summary="Scheduling nuance; human coordinator needed.",
        )
    ).inserted_id

    print({k: str(v) for k, v in ids.items()})


if __name__ == "__main__":
    main()


