from __future__ import annotations

from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database
from dotenv import load_dotenv
import os


load_dotenv()

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        _client = MongoClient(uri, appname="independent-agent")
    return _client


def get_db() -> Database:
    db_name = os.getenv("MONGO_DB_NAME", "misogi")
    return get_client()[db_name]


