from __future__ import annotations

from fastapi import APIRouter

from api.v1.endpoints import auth as auth_endpoints
from api.v1.endpoints import public as public_endpoints
from api.v1.endpoints import webhooks as webhooks_endpoints
from api.v1.endpoints import admin as admin_endpoints


api_router = APIRouter()

# Auth endpoints
api_router.include_router(auth_endpoints.router)
api_router.include_router(public_endpoints.router)
api_router.include_router(webhooks_endpoints.router)
api_router.include_router(admin_endpoints.router)

