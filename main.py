from __future__ import annotations

import logging
from logging.config import dictConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from api.v1.router import api_router
from typing import Any, Dict
import warnings

from fastapi import FastAPI
from pydantic import BaseModel

from agent.graph import run
from bson import ObjectId


from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from email_reply_agent.reply_handler.graph import run_reply_workflow
from services.gmail.processor import process_pubsub_push
from email_reply_agent.reply_handler.config import settings
from services.gmail.client import start_watch, build_gmail_service
from email_reply_agent.reply_handler.db import set_last_history_id, get_last_history_id

try:
    # Suppress urllib3 OpenSSL warning on macOS LibreSSL (harmless for local HTTP)
    from urllib3.exceptions import NotOpenSSLWarning

    warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
except Exception:
    pass


class TriggerPayload(BaseModel):
    patient: Dict[str, Any]
    campaign: Dict[str, Any]

class InboundReply(BaseModel):
    thread_id: str = Field(..., description="Email thread/conversation identifier")
    reply_email_body: str = Field(..., description="Plain text body of the patient's reply")
    patient_email: Optional[str] = Field(None, description="Optional patient email to use if not found in DB")
    patient_name: Optional[str] = Field(None, description="Optional patient name for personalization")

def configure_logging() -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                    "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "level": "INFO",
                }
            },
            "root": {"handlers": ["console"], "level": "INFO"},
            "loggers": {
                "backend": {"handlers": ["console"], "level": "INFO", "propagate": True},
                "email_reply_agent": {"handlers": ["console"], "level": "INFO", "propagate": True},
                "services.gmail": {"handlers": ["console"], "level": "INFO", "propagate": True},
            },
        }
    )


configure_logging()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Mundos AI Backend", version="0.1.0")

    # Configure CORS
    origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").strip()
    allow_all_origins = origins_env in {"*", '"*"'}
    if allow_all_origins:
        # Wildcard: allow all origins, without credentials per CORS spec
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        allowed_origins = [o.strip() for o in origins_env.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(api_router, prefix="/api/v1")

    @app.post("/agent/trigger")
    def trigger_agent(payload: TriggerPayload):
        # print('=============>',payload)
        # Ensure IDs are ObjectId where applicable
        if isinstance(payload.patient.get("_id"), str) and len(payload.patient["_id"]) == 24:
            payload.patient["_id"] = ObjectId(payload.patient["_id"])  # type: ignore
        if isinstance(payload.campaign.get("_id"), str) and len(payload.campaign["_id"]) == 24:
            payload.campaign["_id"] = ObjectId(payload.campaign["_id"])  # type: ignore
        result = run(payload.patient, payload.campaign)


        return {"status": "ok", "keys": list(result.keys())}
    
    @app.post("/gmail/watch/start")
    async def gmail_watch_start():
        if not settings.gmail_topic_name:
            raise HTTPException(status_code=400, detail="GMAIL_TOPIC_NAME not configured")
        try:
            label_ids = [lbl.strip() for lbl in settings.gmail_label_ids_default.split(",") if lbl.strip()]
            resp = start_watch(
                topic_name=settings.gmail_topic_name,
                label_ids=label_ids or ["INBOX"],
                label_filter_action=settings.gmail_label_filter_action_default or "include",
                user_id="me",
            )
            # Resolve actual mailbox email address from Gmail profile
            try:
                svc = build_gmail_service()
                profile = svc.users().getProfile(userId="me").execute()
                email_addr = profile.get("emailAddress")
            except Exception:
                email_addr = settings.gmail_user_email
            baseline_history = resp.get("historyId")
            if baseline_history and email_addr and not get_last_history_id(email_addr):
                set_last_history_id(email_addr, str(baseline_history))
                logger.info("gmail.watch_baseline_saved", extra={"email": email_addr, "historyId": str(baseline_history)})
            return {"ok": True, "watch": resp}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))


    @app.post("/agent/reply")
    async def handle_inbound_reply(payload: InboundReply):
        try:
            result = run_reply_workflow(
                thread_id=payload.thread_id,
                reply_email_body=payload.reply_email_body,
                patient_email=payload.patient_email,
                patient_name=payload.patient_name,
            )
            return {
                "ok": True,
                "intent": result.get("classified_intent"),
                "booking_link": result.get("booking_link"),
                "send_result": result.get("send_result"),
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        
    @app.post("/pubsub/push")
    async def pubsub_push(request: Request):
        token = request.query_params.get("token")
        if settings.pubsub_verification_token and token != settings.pubsub_verification_token:
            raise HTTPException(status_code=403, detail="Invalid token")

        body: Dict[str, Any] = await request.json()
        logger.info("gmail.pubsub_push_received", extra={
            "has_message": bool(body.get("message")),
            "has_attributes": bool((body.get("message") or {}).get("attributes")),
        })
        try:
            result = process_pubsub_push(body)
            logger.info("gmail.pubsub_processed", extra=result)
            return result
        except Exception as exc:
            logger.exception("gmail.pubsub_error")
            return {"ok": False, "error": str(exc)}
        
    @app.on_event("startup")
    async def _auto_watch_start():
        import asyncio, time

        async def start_or_refresh_watch() -> Optional[float]:
            if not settings.gmail_topic_name:
                return None
            try:
                label_ids = [lbl.strip() for lbl in settings.gmail_label_ids_default.split(",") if lbl.strip()]
                resp = start_watch(
                    topic_name=settings.gmail_topic_name,
                    label_ids=label_ids or ["INBOX"],
                    label_filter_action=settings.gmail_label_filter_action_default or "include",
                    user_id="me",
                )
                # Set baseline only if none is stored
                baseline_history = resp.get("historyId")
                # Resolve mailbox email
                try:
                    svc = build_gmail_service()
                    profile = svc.users().getProfile(userId="me").execute()
                    email_addr = profile.get("emailAddress")
                except Exception:
                    email_addr = settings.gmail_user_email
                if baseline_history and email_addr and not get_last_history_id(email_addr):
                    set_last_history_id(email_addr, str(baseline_history))
                    logger.info("gmail.watch_baseline_saved", extra={"email": email_addr, "historyId": str(baseline_history)})
                # Return expiration (ms since epoch) if provided
                exp = resp.get("expiration")
                return float(exp) / 1000.0 if exp else None
            except Exception:
                return None

        async def watch_maintainer():
            while True:
                exp_sec = await start_or_refresh_watch()
                # Compute next refresh time: 10 minutes before expiration, or fallback 12h
                now = time.time()
                if exp_sec:
                    delay = max(300.0, (exp_sec - now) - 600.0)
                else:
                    delay = 12 * 60 * 60
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    break

        app.state._watch_task = __import__("asyncio").create_task(watch_maintainer())

    @app.on_event("shutdown")
    async def _auto_watch_stop():
        task = getattr(app.state, "_watch_task", None)
        if task:
            task.cancel()

    @app.get("/")
    async def root_health() -> dict[str, str]:
        return {"status": "ok"}

    logger.info("Application initialized")
    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)


