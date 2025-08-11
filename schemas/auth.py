from __future__ import annotations

from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: str | None = None
    email: EmailStr | None = None


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: str
    password: str


class UserDisplay(BaseModel):
    user_id: str
    name: str
    email: EmailStr
    role: str

