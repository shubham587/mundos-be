from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BaseRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    @staticmethod
    def _ensure_object_id(value: Any) -> ObjectId:
        if isinstance(value, ObjectId):
            return value
        return ObjectId(str(value))

    async def find_many(
        self,
        collection: str,
        query: Dict[str, Any] | None = None,
        *,
        sort: Optional[Sequence[tuple[str, int]]] = None,
        limit: Optional[int] = None,
        skip: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        cursor = self.db[collection].find(query or {})
        if sort:
            cursor = cursor.sort(list(sort))
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return [doc async for doc in cursor]

    async def count_many(self, collection: str, query: Dict[str, Any] | None = None) -> int:
        return await self.db[collection].count_documents(query or {})

    async def find_one(self, collection: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self.db[collection].find_one(query)

    async def insert_one(self, collection: str, doc: Dict[str, Any], *, with_timestamps: bool = True) -> ObjectId:
        # Special-case: never persist a null _id; MongoDB will auto-generate one
        if doc.get("_id", "__absent__") is None:
            doc = {k: v for k, v in doc.items() if k != "_id"}

        if with_timestamps:
            now = utcnow()
            if doc.get("created_at") is None:
                doc["created_at"] = now
            if doc.get("updated_at") is None:
                doc["updated_at"] = now
        result = await self.db[collection].insert_one(doc)
        return result.inserted_id

    async def update_one(
        self,
        collection: str,
        filter_query: Dict[str, Any],
        update: Dict[str, Any],
        *,
        touch_updated_at: bool = True,
    ) -> None:
        if touch_updated_at:
            update = {**update}
            set_part = update.get("$set", {})
            set_part = {**set_part, "updated_at": utcnow()}
            update["$set"] = set_part
        await self.db[collection].update_one(filter_query, update)

    async def delete_one(self, collection: str, query: Dict[str, Any]) -> None:
        await self.db[collection].delete_one(query)


