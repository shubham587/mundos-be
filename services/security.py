from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
import re

import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import EmailStr

from core.config import settings
from db.database import get_database
from repositories.base import BaseRepository
from models.role import Role


password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
logger = logging.getLogger(__name__)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    ok = password_context.verify(plain_password, hashed_password)
    # Debug log only in development
    if settings.environment == "development":
        logger.info(
            "auth.password_verify",
            extra={
                "plain_len": len(plain_password or ""),
                "hashed_prefix": (hashed_password or "")[:12],
                "result": ok,
            },
        )
    return ok


def get_password_hash(password: str) -> str:
    hashed = password_context.hash(password)
    if settings.environment == "development":
        logger.info(
            "auth.password_hash_preview",
            extra={"plain_len": len(password or ""), "hash_prefix": hashed[:12]},
        )
    return hashed


def create_access_token(subject: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = subject.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


async def get_user_by_email(email: str) -> Optional[Role]:
    # Log which DB we are using for role validation
    logger.info(
        "auth.db_resolved",
        extra={"mongo_uri": settings.mongo_uri, "database": settings.database_name, "collection": "roles"},
    )
    db = await get_database()
    repo = BaseRepository(db)
    # Case-insensitive exact match on email to avoid login failures due to casing
    email_ci = {"$regex": f"^{re.escape(str(email))}$", "$options": "i"}
    doc = await repo.find_one("roles", {"email": email_ci})
    if not doc:
        logger.warning("auth.user_not_found", extra={"email": email})
        return None
    return Role(**doc)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> Role:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        email: str | None = payload.get("email")
        if email is None:
            logger.error("auth.token_missing_email")
            raise credentials_exception
    except JWTError:
        logger.exception("auth.jwt_error")
        raise credentials_exception

    user = await get_user_by_email(email)
    if user is None:
        logger.error("auth.user_not_found_for_token", extra={"email": email})
        raise credentials_exception
    return user


async def create_initial_admin_if_missing(name: str, email: EmailStr, role: str, password: str) -> Role:
    db = await get_database()
    repo = BaseRepository(db)
    existing = await repo.find_one("roles", {"email": str(email)})
    if existing:
        return Role(**existing)
    hashed = get_password_hash(password)
    doc = {"name": name, "email": str(email), "role": role, "hashed_password": hashed}
    inserted_id = await repo.insert_one("roles", doc)
    doc.update({"_id": inserted_id})
    return Role(**doc)

