from __future__ import annotations

from functools import lru_cache
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import MongoClient
from pymongo.database import Database as SyncDatabase

from core.config import settings

# ---------------- Async (FastAPI) ----------------

@lru_cache(maxsize=1)
def get_motor_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(settings.mongo_uri)


async def get_database() -> AsyncIOMotorDatabase:
    client = get_motor_client()
    return client[settings.database_name]


async def close_database() -> None:
    client = get_motor_client()
    client.close()

# ---------------- Sync (Agents / Cron) ----------------

_sync_client: Optional[MongoClient] = None


def get_sync_client() -> MongoClient:
    global _sync_client
    if _sync_client is None:
        # Reuse same URI + DB name from settings for consistency
        _sync_client = MongoClient(settings.mongo_uri, appname="agent-runtime")
    return _sync_client


def get_sync_database() -> SyncDatabase:
    return get_sync_client()[settings.database_name]


def close_sync_database() -> None:
    global _sync_client
    if _sync_client is not None:
        _sync_client.close()
        _sync_client = None