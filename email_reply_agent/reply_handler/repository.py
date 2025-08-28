# Helper functions for the email reply agent.
# Central place to read/update campaigns, interactions, patients, and Gmail sync state.
# Covers:
# - finding patients & latest campaigns
# - updating campaign status / follow-up progress
# - storing interactions (optional AI intent & sentiment)
# - maintaining engagement summaries
# - tracking Gmail history & processed message IDs (avoid duplicates)
from __future__ import annotations

from typing import Any, Optional, Dict
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from pymongo import DESCENDING

from db.database import get_sync_database  # unified sync DB
from .config import settings

def _db():
    return get_sync_database()

def get_campaign_collection():
    name = getattr(settings, "mongodb_campaign_collection", "campaigns")
    return _db()[name]

def get_interaction_collection():
    return _db()["interactions"]

def get_gmail_state_collection():
    return _db()["gmail_states"]

def get_gmail_processed_collection():
    return _db()["gmail_processed"]

def get_patient_collection():
    return _db()["patients"]

# Lookups
def find_patient_by_email(email: str) -> Optional[Dict[str, Any]]:
    if not email:
        return None
    return get_patient_collection().find_one({"email": {"$regex": f"^{email}$", "$options": "i"}})

def find_latest_campaign_by_patient_id(patient_id: ObjectId) -> Optional[Dict[str, Any]]:
    return get_campaign_collection().find_one({"patient_id": patient_id}, sort=[("updated_at", DESCENDING)])

# Updates
def ensure_campaign_thread_id(campaign_id: ObjectId, thread_id: Optional[str]) -> None:
    if not thread_id:
        return
    get_campaign_collection().update_one(
        {"_id": campaign_id},
        {"$set": {"channel.thread_id": thread_id, "updated_at": datetime.now(timezone.utc)}},
    )

def set_campaign_form_sent(campaign_id: ObjectId, link_url: str, reply_thread_id: str) -> None:
    now = datetime.now(timezone.utc)
    get_campaign_collection().update_one(
        {"_id": campaign_id},
        {
            "$set": {
                "status": "BOOKING_INITIATED",
                "follow_up_details.next_attempt_at": now + timedelta(days=1),
                "follow_up_details.attempts_made": 1,
                "booking_funnel.status": "FORM_SENT",
                "booking_funnel.link_url": link_url,
                "channel.thread_id": reply_thread_id,
                "updated_at": now,
            }
        },
    )

def set_campaign_declined(campaign_id: ObjectId) -> None:
    now = datetime.now(timezone.utc)
    get_campaign_collection().update_one(
        {"_id": campaign_id},
        {"$set": {"status": "RECOVERY_DECLINED", "updated_at": now}},
    )

def set_campaign_handoff_required(campaign_id: ObjectId) -> None:
    now = datetime.now(timezone.utc)
    get_campaign_collection().update_one(
        {"_id": campaign_id},
        {"$set": {"status": "HANDOFF_REQUIRED", "updated_at": now}},
    )

def set_campaign_re_engaged(campaign_id: ObjectId) -> None:
    now = datetime.now(timezone.utc)
    get_campaign_collection().update_one(
        {"_id": campaign_id},
        {
            "$set": {
                "status": "RE_ENGAGED",
                "updated_at": now,
                "follow_up_details.next_attempt_at": now + timedelta(days=3),
                "follow_up_details.attempts_made": 2,
            }
        },
    )

def insert_interaction(
    *,
    campaign_id: ObjectId,
    direction: str,
    content: str,
    intent: Optional[str] = None,
    sentiment: Optional[str] = None,
) -> Any:
    doc: Dict[str, Any] = {
        "campaign_id": campaign_id,
        "direction": direction,
        "content": content,
        "ai_analysis": {},
        "timestamp": datetime.now(timezone.utc),
    }
    if intent is not None or sentiment is not None:
        doc["ai_analysis"] = {k: v for k, v in {"intent": intent, "sentiment": sentiment}.items() if v is not None}
    return get_interaction_collection().insert_one(doc)

def fetch_interactions_for_campaign(campaign_id: ObjectId) -> list[Dict[str, Any]]:
    return list(get_interaction_collection().find({"campaign_id": campaign_id}).sort("timestamp", 1))

def update_engagement_summary(campaign_id: ObjectId, summary: str) -> None:
    get_campaign_collection().update_one(
        {"_id": campaign_id},
        {"$set": {"engagement_summary": summary, "updated_at": datetime.now(timezone.utc)}},
    )

# Gmail processing state
def get_last_history_id(email_address: str) -> Optional[str]:
    doc = get_gmail_state_collection().find_one({"emailAddress": email_address})
    return doc.get("historyId") if doc else None

def set_last_history_id(email_address: str, history_id: str) -> None:
    get_gmail_state_collection().update_one(
        {"emailAddress": email_address},
        {"$set": {"emailAddress": email_address, "historyId": history_id, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

def has_processed_message(email_address: str, gmail_message_id: str) -> bool:
    return get_gmail_processed_collection().find_one({"emailAddress": email_address, "gmailMessageId": gmail_message_id}) is not None

def mark_processed_message(email_address: str, gmail_message_id: str, thread_id: Optional[str] = None) -> None:
    get_gmail_processed_collection().update_one(
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