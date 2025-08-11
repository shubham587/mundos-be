from __future__ import annotations

from datetime import datetime
from enum import Enum

from typing import Optional

from pydantic import BaseModel

from .base import MongoModel, PyObjectId


class Direction(str, Enum):
    outgoing = "outgoing"
    incoming = "incoming"


class AIAnalysis(BaseModel):
    intent: Optional[str] = None
    sentiment: Optional[str] = None


class Interaction(MongoModel):
    campaign_id: PyObjectId
    direction: Direction
    content: str
    ai_analysis: Optional[AIAnalysis] = None
    timestamp: Optional[datetime] = None

