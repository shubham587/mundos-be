# 

from __future__ import annotations

import os
import requests
from datetime import datetime
from enum import Enum

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, WriteError
from models.patient import Patient as PatientModel, PatientType
from models.campaign import (
    Campaign as CampaignModel,
    CampaignType,
    CampaignStatus,
    FollowUpDetails,
    Channel as ChannelModel,
    BookingFunnel as BookingFunnelModel,
    BookingFunnelStatus,
)


load_dotenv()


def get_db():
    client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    return client[os.getenv("MONGO_DB_NAME", "misogi")]


def find_due_campaigns(db, limit: int = 50):
    now = datetime.utcnow()
    return list(
        db.campaigns.find(
            {
                # Only first-touch emails to cold leads (RECOVERY) are handled by this job
                "campaign_type": "RECOVERY",
                "status": "ATTEMPTING_RECOVERY",
                "follow_up_details.attempts_made": 0,
                "follow_up_details.next_attempt_at": {"$lte": now},
            }
        ).limit(limit)
    )


def _normalize_service_name(name: str) -> str:
    allowed = {
        "dental_implants": "dental_implants",
        "Dental crowns": "Dental crowns",
        "Veneers": "Veneers",
        "Teeth whitening": "Teeth whitening",
        "Routine dental work": "Routine dental work",
    }
    return allowed.get(name, name)


def _to_mongo(data):
    # Convert Enums to their .value and recurse; keep datetime as datetime
    if isinstance(data, Enum):
        return data.value
    if isinstance(data, dict):
        return {k: _to_mongo(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_to_mongo(x) for x in data]
    return data


def upsert_patient_from_lead(db, lead: dict):
    now = datetime.utcnow()
    email = (lead.get("email") or "").strip().lower()
    phone = lead.get("phone", "")
    name = (lead.get("name") or "").strip()
    # Build full patient document via models, with all fields present
    patient_model = PatientModel(
        name=name,
        email=email,
        phone=phone or None,
        patient_type=PatientType.COLD_LEAD,
        preferred_channel=["email"],
        treatment_history=None,
        created_at=now,
        updated_at=now,
    )
    # If already exists, just update timestamp and return existing id
    existing = db.patients.find_one({"email": email}, {"_id": 1})
    if existing and existing.get("_id"):
        db.patients.update_one({"_id": existing["_id"]}, {"$set": {"updated_at": now}})
        return existing["_id"]

    # Prepare clean insert payload: avoid conflicting or invalid fields
    to_insert_full = _to_mongo(patient_model.model_dump(by_alias=True, exclude_none=False))
    to_insert = dict(to_insert_full)
    to_insert.pop("_id", None)
    to_insert.pop("email", None)
    to_insert.pop("updated_at", None)

    try:
        res = db.patients.find_one_and_update(
            {"email": email},
            {
                "$setOnInsert": to_insert,
                "$set": {"email": email, "updated_at": now},
            },
            upsert=True,
            return_document=True,
        )
        return res["_id"]
    except (DuplicateKeyError, WriteError):
        # Likely inserted concurrently or a conflicting operator; fetch existing by email
        existing = db.patients.find_one({"email": email}, {"_id": 1})
        if existing and existing.get("_id"):
            return existing["_id"]
        return None


def ensure_recovery_campaign(db, patient_id: ObjectId, service_name: str):
    now = datetime.utcnow()
    service = _normalize_service_name(service_name)
    existing = db.campaigns.find_one(
        {
            "patient_id": patient_id,
            "service_name": service,
            "status": "ATTEMPTING_RECOVERY",
            "campaign_type": "RECOVERY",
        }
    )
    if existing:
        return existing["_id"]

    camp_model = CampaignModel(
        patient_id=patient_id,
        campaign_type=CampaignType.RECOVERY,
        service_name=service,
        status=CampaignStatus.ATTEMPTING_RECOVERY,
        channel=ChannelModel(type="email", thread_id=None),
        booking_funnel=None,
        engagement_summary=None,
        follow_up_details=FollowUpDetails(
            attempts_made=0,
            max_attempts=3,
            next_attempt_at=now,
        ),
        created_at=now,
        updated_at=now,
    )
    payload = _to_mongo(camp_model.model_dump(by_alias=True, exclude_none=True))
    payload.pop("_id", None)
    result = db.campaigns.insert_one(payload)
    return result.inserted_id


def ingest_leads(db, limit: int = 100) -> int:
    leads = list(db.leads.find({"processed": {"$ne": True}}).limit(limit))
    if not leads:
        return 0
    created = 0
    for lead in leads:
        try:
            patient_id = upsert_patient_from_lead(db, lead)
            if not patient_id:
                # Skip gracefully if we couldn't resolve a valid patient id
                continue
            ensure_recovery_campaign(db, patient_id, lead.get("service_name", "dental_implants"))
            db.leads.update_one(
                {"_id": lead["_id"]},
                {"$set": {"processed": True, "processed_at": datetime.utcnow()}},
            )
            created += 1
        except Exception as exc:
            print(f"[CRON] Lead ingest failed lead={lead.get('_id')}: {exc}")
    print(f"[CRON] Ingested {created} leads into patients/campaigns")
    return created


def _to_jsonable(data):
    from datetime import datetime
    from enum import Enum

    if isinstance(data, ObjectId):
        return str(data)
    if isinstance(data, datetime):
        return data.isoformat()
    if isinstance(data, Enum):
        return data.value
    if isinstance(data, dict):
        return {k: _to_jsonable(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_to_jsonable(x) for x in data]
    return data


def main():
    base_url = os.getenv("AGENT_API_BASE_URL", "http://127.0.0.1:3000")
    db = get_db()
    # Step 1: ingest new leads
    ingest_leads(db, limit=200)
    due = find_due_campaigns(db, limit=100)
    for camp in due:
        patient = db.patients.find_one({"_id": camp["patient_id"]})
        if not patient:
            continue
        payload = {
            "patient": _to_jsonable(patient),
            "campaign": _to_jsonable(camp),
        }
        try:
            r = requests.post(f"{base_url}/api/v1/agent/trigger", json=payload, timeout=20)
            print(f"[CRON] Triggered campaign={camp['_id']} status={r.status_code}")
        except Exception as exc:
            print(f"[CRON] Failed to trigger campaign={camp['_id']}: {exc}")


if __name__ == "__main__":
    main()

