from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Request
import logging
from fastapi.security import OAuth2PasswordRequestForm

from schemas.auth import Token, UserDisplay
from core.config import settings
from services.security import (
    create_access_token,
    get_current_user,
    get_user_by_email,
    verify_password,
)


router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/auth/login", response_model=Token)
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    # Request-level diagnostics
    logger.info(
        "auth.login_request",
        extra={
            "method": request.method,
            "path": str(request.url.path),
            "content_type": request.headers.get("content-type"),
            "accept": request.headers.get("accept"),
            "user_agent": request.headers.get("user-agent"),
        },
    )

    username = (form_data.username or "").strip()
    logger.info(
        "auth.login_attempt",
        extra={
            "email": username,
            "grant_type": form_data.grant_type,
            "scopes": ",".join(form_data.scopes) if getattr(form_data, "scopes", None) else "",
            "client_id_present": bool(getattr(form_data, "client_id", None)),
            "client_secret_present": bool(getattr(form_data, "client_secret", None)),
        },
    )
    if settings.environment == "development":
        # WARNING: logs raw password for debugging in dev only
        logger.info(
            "auth.login_form_payload",
            extra={"email": username, "password": form_data.password, "password_length": len(form_data.password or "")},
        )
    user = await get_user_by_email(username)
    logger.info("auth.user_lookup", extra={"email": username, "found": bool(user)})
    if not user:
        logger.warning("auth.login_user_not_found", extra={"email": username})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    pwd_ok = verify_password(form_data.password, user.hashed_password)
    if not pwd_ok:
        logger.warning("auth.login_invalid_password", extra={"email": username})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    access_token = create_access_token({"email": user.email})
    logger.info("auth.login_success", extra={"email": user.email})
    return Token(access_token=access_token)


@router.get("/users/me", response_model=UserDisplay)
async def read_users_me(current_user=Depends(get_current_user)) -> UserDisplay:
    return UserDisplay(user_id=str(current_user.id), name=current_user.name, email=current_user.email, role=current_user.role)

