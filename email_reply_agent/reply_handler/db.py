from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import MongoClient, DESCENDING
from .config import settings
from dotenv import load_dotenv

load_dotenv()

_client: Optional[MongoClient] = None


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.mongodb_uri)
    return _client


def get_db():
    client = get_mongo_client()
    return client[settings.mongodb_db_name]


def get_campaign_collection():
    return get_db()[settings.mongodb_campaign_collection]


def get_interaction_collection():
    return get_db()["interactions"]


def get_gmail_state_collection():
    return get_db()["gmail_states"]


def get_gmail_processed_collection():
    return get_db()["gmail_processed"]


def get_patient_collection():
    return get_db()["patients"]


# Lookups

def find_patient_by_email(email: str) -> Optional[dict[str, Any]]:
    if not email:
        return None
    coll = get_patient_collection()
    patient = coll.find_one({"email": {"$regex": f"^{email}$", "$options": "i"}})
    return patient


def find_latest_campaign_by_patient_id(patient_id: ObjectId) -> Optional[dict[str, Any]]:
    coll = get_campaign_collection()
    # Prefer most recently updated
    campaign = coll.find_one({"patient_id": patient_id}, sort=[("updated_at", DESCENDING)])
    return campaign


def find_campaign_by_thread_id(thread_id: str) -> Optional[dict[str, Any]]:
    coll = get_campaign_collection()
    campaign = coll.find_one({"channel.thread_id": thread_id})
    return campaign


# Updates

def ensure_campaign_thread_id(campaign_id: ObjectId, thread_id: Optional[str]) -> None:
    if not thread_id:
        return
    coll = get_campaign_collection()
    coll.update_one(
        {"_id": campaign_id},
        {"$set": {"channel.thread_id": thread_id, "updated_at": datetime.now(timezone.utc)}},
    )


def set_campaign_form_sent(campaign_id: ObjectId, link_url: str, reply_thread_id: str) -> None:
    coll = get_campaign_collection()
    now = datetime.now(timezone.utc)
    coll.update_one(
        {"_id": campaign_id},
        {
            "$set": {
                "status": "BOOKING_INITIATED",
                "booking_funnel.status": "FORM_SENT",
                "booking_funnel.link_url": link_url,
                "channel.thread_id": reply_thread_id,
                "updated_at": now,
            }
        },
    )


def set_campaign_declined(campaign_id: ObjectId) -> None:
    coll = get_campaign_collection()
    now = datetime.now(timezone.utc)
    coll.update_one(
        {"_id": campaign_id},
        {"$set": {"status": "RECOVERY_DECLINED", "updated_at": now}},
    )


def set_campaign_handoff_required(campaign_id: ObjectId) -> None:
    coll = get_campaign_collection()
    now = datetime.now(timezone.utc)
    coll.update_one(
        {"_id": campaign_id},
        {"$set": {"status": "HANDOFF_REQUIRED", "updated_at": now}},
    )


def insert_interaction(
    *,
    campaign_id: ObjectId,
    direction: str,
    content: str,
    intent: Optional[str] = None,
    sentiment: Optional[str] = None,
) -> Any:
    coll = get_interaction_collection()
    doc: dict[str, Any] = {
        "campaign_id": campaign_id,
        "direction": direction,
        "content": content,
        "ai_analysis": {},
        "timestamp": datetime.now(timezone.utc),
    }
    if intent is not None or sentiment is not None:
        doc["ai_analysis"] = {k: v for k, v in {"intent": intent, "sentiment": sentiment}.items() if v is not None}
    return coll.insert_one(doc)


def fetch_interactions_for_campaign(campaign_id: ObjectId) -> list[dict[str, Any]]:
    coll = get_interaction_collection()
    return list(coll.find({"campaign_id": campaign_id}).sort("timestamp", 1))


def update_engagement_summary(campaign_id: ObjectId, summary: str) -> None:
    coll = get_campaign_collection()
    coll.update_one(
        {"_id": campaign_id},
        {"$set": {"engagement_summary": summary, "updated_at": datetime.now(timezone.utc)}},
    )


# Gmail processing state

def get_last_history_id(email_address: str) -> Optional[str]:
    coll = get_gmail_state_collection()
    doc = coll.find_one({"emailAddress": email_address})
    return doc.get("historyId") if doc else None


def set_last_history_id(email_address: str, history_id: str) -> None:
    coll = get_gmail_state_collection()
    coll.update_one(
        {"emailAddress": email_address},
        {"$set": {"emailAddress": email_address, "historyId": history_id, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


def has_processed_message(email_address: str, gmail_message_id: str) -> bool:
    coll = get_gmail_processed_collection()
    doc = coll.find_one({"emailAddress": email_address, "gmailMessageId": gmail_message_id})
    return doc is not None


def mark_processed_message(email_address: str, gmail_message_id: str, thread_id: Optional[str] = None) -> None:
    coll = get_gmail_processed_collection()
    coll.update_one(
        {"emailAddress": email_address, "gmailMessageId": gmail_message_id},
        {
            "$set": {
                "emailAddress": email_address,
                "gmailMessageId": gmail_message_id,
                "threadId": thread_id,
                "processed_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
