from __future__ import annotations

from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from core.config import settings


@lru_cache(maxsize=1)
def get_motor_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(settings.mongo_uri)


async def get_database() -> AsyncIOMotorDatabase:
    client = get_motor_client()
    return client[settings.database_name]


async def close_database() -> None:
    client = get_motor_client()
    client.close()

