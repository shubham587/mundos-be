from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient

from backend.core.config import settings


UTC = timezone.utc


async def upsert_patient(db, name: str, email: str, phone: str) -> str:
    existing = await db["patients"].find_one({"email": email})
    if existing:
        return str(existing["_id"])
    doc = {
        "name": name,
        "email": email,
        "phone": phone,
        "patient_type": "COLD_LEAD",
        "preferred_channel": ["email"],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    res = await db["patients"].insert_one(doc)
    return str(res.inserted_id)


async def create_campaign(
    db,
    *,
    patient_id,
    campaign_type: str,
    status: Optional[str],
    engagement_summary: Optional[str] = None,
    handoff_required: bool = False,
) -> str:
    campaign_doc = {
        "patient_id": patient_id,
        "campaign_type": campaign_type,
        "status": status,
        "engagement_summary": engagement_summary,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    if handoff_required:
        campaign_doc["status"] = "HANDOFF_REQUIRED"
    res = await db["campaigns"].insert_one(campaign_doc)
    return str(res.inserted_id)


async def add_interaction(db, *, campaign_id, direction: str, content: str, minutes_ago: int = 30) -> None:
    doc = {
        "campaign_id": campaign_id,
        "direction": direction,
        "content": content,
        "timestamp": datetime.now(UTC) - timedelta(minutes=minutes_ago),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    await db["interactions"].insert_one(doc)


async def main() -> None:
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.database_name]
    try:
        # Patient 1 - HANDOFF_REQUIRED with rich conversation
        p1 = await upsert_patient(db, "Emily Johnson", "emily.johnson@example.com", "+1 (555) 987-6543")
        c1 = await create_campaign(
            db,
            patient_id=p1,
            campaign_type="RECOVERY",
            status="HANDOFF_REQUIRED",
            engagement_summary="Insurance verification needed; AI agent reached limit.",
            handoff_required=True,
        )
        await add_interaction(db, campaign_id=c1, direction="incoming", content="Hi, can you check if my plan covers root canal?", minutes_ago=120)
        await add_interaction(db, campaign_id=c1, direction="outgoing", content="I can help with general queries. Which insurer do you have?", minutes_ago=115)
        await add_interaction(db, campaign_id=c1, direction="incoming", content="Aetna PPO.", minutes_ago=110)
        await add_interaction(db, campaign_id=c1, direction="outgoing", content="Thanks! I will connect you to a human to verify specific benefits.", minutes_ago=105)
        await add_interaction(db, campaign_id=c1, direction="incoming", content="Great, please have someone call me.", minutes_ago=100)

        # Patient 2 - HANDOFF_REQUIRED with multiple back-and-forth messages
        p2 = await upsert_patient(db, "Robert Chen", "robert.chen@example.com", "+1 (555) 456-7890")
        c2 = await create_campaign(
            db,
            patient_id=p2,
            campaign_type="RECOVERY",
            status="HANDOFF_REQUIRED",
            engagement_summary="Scheduling constraints require human support.",
            handoff_required=True,
        )
        await add_interaction(db, campaign_id=c2, direction="incoming", content="Do you have evening appointments?", minutes_ago=75)
        await add_interaction(db, campaign_id=c2, direction="outgoing", content="Our automated scheduler shows 5pm as the latest today.", minutes_ago=70)
        await add_interaction(db, campaign_id=c2, direction="incoming", content="I need 7pm or later.", minutes_ago=65)
        await add_interaction(db, campaign_id=c2, direction="outgoing", content="I'll escalate to a human coordinator for extended hours.", minutes_ago=60)
        await add_interaction(db, campaign_id=c2, direction="incoming", content="Thank you.", minutes_ago=55)

        print("Seeded handoff data:")
        print({
            "patient_ids": [p1, p2],
            "campaign_ids": [c1, c2],
        })
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())


