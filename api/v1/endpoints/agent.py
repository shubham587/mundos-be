from __future__ import annotations

from typing import Any, Dict, Optional
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from bson import ObjectId

from agent.graph import run as run_agent_graph
from email_reply_agent.reply_handler.graph import run_reply_workflow
from services.gmail.processor import process_pubsub_push
from core.config import settings
from services.gmail.client import start_watch, build_gmail_service
from repositories.agent_data import set_last_history_id, get_last_history_id

logger = logging.getLogger(__name__)

router = APIRouter()


class TriggerPayload(BaseModel):
    patient: Dict[str, Any]
    campaign: Dict[str, Any]


class InboundReply(BaseModel):
    thread_id: str = Field(..., description="Email thread/conversation identifier")
    reply_email_body: str = Field(..., description="Plain text body of the patient's reply")
    patient_email: Optional[str] = Field(None, description="Optional patient email to use if not found in DB")
    patient_name: Optional[str] = Field(None, description="Optional patient name for personalization")


@router.post("/agent/trigger")
def trigger_agent(payload: TriggerPayload):
    # Ensure IDs are ObjectId where applicable
    if isinstance(payload.patient.get("_id"), str) and len(payload.patient["_id"]) == 24:
        payload.patient["_id"] = ObjectId(payload.patient["_id"])  # type: ignore
    if isinstance(payload.campaign.get("_id"), str) and len(payload.campaign["_id"]) == 24:
        payload.campaign["_id"] = ObjectId(payload.campaign["_id"])  # type: ignore
    result = run_agent_graph(payload.patient, payload.campaign)
    return {"status": "ok", "keys": list(result.keys())}


@router.post("/gmail/watch/start")
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
            logger.info(
                "gmail.watch_baseline_saved",
                extra={"email": email_addr, "historyId": str(baseline_history)},
            )
        return {"ok": True, "watch": resp}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/agent/reply")
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


@router.post("/pubsub/push")
async def pubsub_push(request: Request):
    body: Dict[str, Any] = await request.json()
    token = request.query_params.get("token")
    if settings.pubsub_verification_token and token != settings.pubsub_verification_token:
        raise HTTPException(status_code=403, detail="Invalid token")

    logger.info(
        "gmail.pubsub_push_received",
        extra={
            "has_message": bool(body.get("message")),
            "has_attributes": bool((body.get("message") or {}).get("attributes")),
        },
    )
    try:
        result = process_pubsub_push(body)
        logger.info("gmail.pubsub_processed", extra=result)
        return result
    except Exception as exc:  # pragma: no cover
        logger.exception("gmail.pubsub_error")
        return {"ok": False, "error": str(exc)}
