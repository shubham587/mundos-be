from __future__ import annotations

import asyncio
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext

from backend.core.config import settings


password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def upsert_admin(
    *, name: str, email: str, role: str = "admin", password: str
) -> dict:
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.database_name]
    try:
        existing: Optional[dict] = await db["roles"].find_one({"email": email})
        if existing:
            return existing
        hashed_password = password_context.hash(password)
        doc = {"name": name, "email": email, "role": role, "hashed_password": hashed_password}
        result = await db["roles"].insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
    finally:
        client.close()


if __name__ == "__main__":
    # Defaults are safe demo values; edit if needed before running.
    admin_name = "Dr. Admin"
    admin_email = "admin@example.com"
    admin_password = "password"

    created = asyncio.run(
        upsert_admin(name=admin_name, email=admin_email, password=admin_password)
    )
    print("Seeded admin:", {k: (str(v) if k == "_id" else v) for k, v in created.items()})


