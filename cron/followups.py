from __future__ import annotations

import os
import requests
from datetime import datetime
from typing import Any, Dict

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient


load_dotenv()


def get_db():
    client = MongoClient(os.getenv("MONGO_URI", "mongodb+srv://algoholics06:Algoholics06@cluster0.iuxnwdd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"))
    return client[os.getenv("MONGO_DB_NAME", "AI-lead-recovery")]


def _to_jsonable(data: Any) -> Any:
    from datetime import datetime as _dt
    from enum import Enum
    if isinstance(data, ObjectId):
        return str(data)
    if isinstance(data, _dt):
        return data.isoformat()
    if isinstance(data, Enum):
        return data.value
    if isinstance(data, dict):
        return {k: _to_jsonable(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_to_jsonable(x) for x in data]
    return data


def find_due_campaigns(db, limit: int = 200):
    now = datetime.utcnow()
    return list(
        db.campaigns.find(
            {
                "campaign_type": {"$in": ["RECOVERY", "RECALL", "APPOINTMENT_REMINDER"]},
                "status": {"$nin": ["RECOVERED", "RECOVERY_FAILED"]},
                "follow_up_details.next_attempt_at": {"$lte": now},
                "$expr": {"$lt": ["$follow_up_details.attempts_made", "$follow_up_details.max_attempts"]},
            }
        ).limit(limit)
    )


def process_due_followups(limit: int = 200) -> int:
    db = get_db()
    base_url = os.getenv("AGENT_API_BASE_URL", "http://192.168.0.99:8000")
    due = find_due_campaigns(db, limit=limit)
    print(f"[CRON:FOLLOWUPS] Found {len(due)} due campaigns")

    processed = 0
    for camp in due:
        patient = db.patients.find_one({"_id": camp["patient_id"]})
        if not patient:
            continue
        payload: Dict[str, Any] = {
            "patient": _to_jsonable(patient),
            "campaign": _to_jsonable(camp),
        }
        try:
            r = requests.post(f"{base_url}/api/v1/agent/trigger", json=payload, timeout=20)
            print(f"[CRON:FOLLOWUPS] POST campaign={camp['_id']} status={r.status_code}")
            processed += 1
        except Exception as exc:
            print(f"[CRON:FOLLOWUPS] Failed campaign={camp['_id']}: {exc}")

    print(f"[CRON:FOLLOWUPS] Processed {processed} campaigns")
    return processed


def main() -> None:
    process_due_followups(limit=int(os.getenv("FOLLOWUPS_LIMIT", "200")))


if __name__ == "__main__":
    main()


