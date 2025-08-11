from __future__ import annotations

from .base import MongoModel


class Role(MongoModel):
    name: str
    email: str
    role: str
    hashed_password: str

