from __future__ import annotations

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from bson import ObjectId

from agent.db import get_db
from agent.services import EmailService, LLMService
from zoneinfo import ZoneInfo
import os


def node_follow_up(state: Dict[str, Any]) -> Dict[str, Any]:
    campaign = state["campaign"]
    patient = state["patient"]
    follow = campaign.get("follow_up_details", {})

    attempts_made: int = int(follow.get("attempts_made", 0))
    max_attempts: int = int(follow.get("max_attempts", 0))
    next_attempt_at: Optional[datetime] = follow.get("next_attempt_at")
    status_value: str = campaign.get("status")
    booking = campaign.get("booking_funnel") or {}
    booking_status_value: Optional[str] = booking.get("status")
    campaign_type_value: str = campaign.get("campaign_type", "RECOVERY")
    service_name_value: str = campaign.get("service_name")

    # attempts guard (>=)
    if attempts_made >= max_attempts:
        state["skip"] = True
        print(
            f"[NODE:FOLLOW_UP] Skipping (attempts_made={attempts_made} >= max_attempts={max_attempts})"
        )
        return state

    llm = LLMService()
    tz = ZoneInfo(os.getenv("TZ", "UTC"))

    # Appointment reminder only once
    if campaign_type_value == "APPOINTMENT_REMINDER":
        local_dt_str = ""
        # Prefer appointment_date from appointments collection for precise date/time
        try:
            db = get_db()
            raw_cid = campaign.get("_id")
            cid = raw_cid if isinstance(raw_cid, ObjectId) else ObjectId(str(raw_cid))
            appt = db.appointments.find_one({"campaign_id": cid})
            appt_dt = appt.get("appointment_date") if appt else None
            print(
                "[REMINDER] Appointment lookup:",
                {
                    "campaign_id": str(cid),
                    "appointment_found": bool(appt),
                    "appointment_date": (appt_dt.isoformat() if hasattr(appt_dt, "isoformat") else str(appt_dt)),
                },
            )
            if isinstance(appt_dt, datetime):
                from zoneinfo import ZoneInfo as _Z
                local_dt_str = appt_dt.replace(tzinfo=_Z("UTC")).astimezone(tz).strftime("%a, %d %b %Y %I:%M %p %Z")
        except Exception:
            # Fallback to next_attempt_at if appointment not found
            try:
                if isinstance(next_attempt_at, datetime):
                    from zoneinfo import ZoneInfo as _Z
                    local_dt_str = next_attempt_at.replace(tzinfo=_Z("UTC")).astimezone(tz).strftime("%a, %d %b %Y %I:%M %p %Z")
            except Exception:
                local_dt_str = ""
        print(
            "[REMINDER] Prepared reminder context:",
            {
                "patient_name": patient.get("name"),
                "tz": str(tz),
                "local_dt_str": local_dt_str,
            },
        )
        body = llm.generate_appointment_reminder_message(
            patient_name=patient["name"], appointment_dt_local_str=local_dt_str
        )
        subject = "Appointment reminder"
    else:
        # RECOVERY / RECALL: skip if recovered/failed or form submitted
        if status_value in {"RECOVERED", "RECOVERY_FAILED"}:
            state["skip"] = True
            return state
        if booking_status_value == "FORM_SUBMITTED":
            state["skip"] = True
            return state

        ai_summary_text: Optional[str] = campaign.get("engagement_summary")
        body = llm.generate_campaign_message(
            patient_name=patient["name"],
            campaign_type=campaign_type_value,
            attempts_made=attempts_made,
            service_name=service_name_value,
            ai_summary=ai_summary_text,
        )
        subject = f"Following up about {service_name_value}"
    # print('=============>',body)
    state["email_body"] = body
    state["subject"] = subject
    print(
        "[NODE:FOLLOW_UP] Prepared email:",
        {
            "patient_email": patient.get("email"),
            "campaign_id": str(campaign.get("_id")),
            "service_name": service_name_value,
            "subject": subject,
            "body_preview": (body[:120] + ("…" if len(body) > 120 else "")),
        },
    )
    return state




def node_send_email(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("skip"):
        return state
    email = EmailService()
    email.send(state["patient"]["email"], state.get("subject", "Follow up"), state.get("email_body", ""))

    # log interaction
    db = get_db()
    ins = db.interactions.insert_one(
        {
            "campaign_id": ObjectId(state["campaign"]["_id"]),
            "direction": "outgoing",
            "content": state.get("email_body", ""),
            "timestamp": datetime.utcnow(),
        }
    )
    print(
        "[NODE:SEND_EMAIL] Logged interaction:",
        {"interaction_id": str(ins.inserted_id), "campaign_id": str(state["campaign"]["_id"])},
    )
    return state


def node_ai_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    campaign_id = ObjectId(state["campaign"]["_id"])
    db = get_db()
    interactions = list(db.interactions.find({"campaign_id": campaign_id}).sort("timestamp", 1))
    chat_items: List[Dict[str, Any]] = [
        {
            "timestamp_iso": (i.get("timestamp").isoformat() if hasattr(i.get("timestamp"), "isoformat") else str(i.get("timestamp"))),
            "direction": i.get("direction"),
            "content": i.get("content", ""),
        }
        for i in interactions
    ]

    llm = LLMService()
    summary = llm.summarize_formatted(chat_items)
    db.campaigns.update_one({"_id": campaign_id}, {"$set": {"engagement_summary": summary}})

    # increment attempt and schedule next per type
    camp = db.campaigns.find_one({"_id": campaign_id}, {"campaign_type": 1, "follow_up_details": 1})
    ctype = (camp or {}).get("campaign_type", "RECOVERY")
    if ctype == "RECALL":
        days = 5
    elif ctype == "APPOINTMENT_REMINDER":
        days = 0
    else:
        days = 5
    inc_res = db.campaigns.find_one_and_update(
        {"_id": campaign_id},
        {"$inc": {"follow_up_details.attempts_made": 1}},
        return_document=True,
    )
    attempts_made = (inc_res or {}).get("follow_up_details", {}).get("attempts_made", 0)
    max_attempts = (inc_res or {}).get("follow_up_details", {}).get("max_attempts", 0)
    if attempts_made < max_attempts and days > 0:
        db.campaigns.update_one(
            {"_id": campaign_id},
            {"$set": {"follow_up_details.next_attempt_at": datetime.utcnow() + timedelta(days=days)}},
        )

    updated = db.campaigns.find_one({"_id": campaign_id}, {"follow_up_details": 1, "engagement_summary": 1})
    print(
        "[NODE:AI_SUMMARY] Summary + follow-up update:",
        {
            "campaign_id": str(campaign_id),
            "interactions": len(interactions),
            "summary_preview": (summary[:180] + ("…" if len(summary) > 180 else "")),
            "follow_up_details": updated.get("follow_up_details") if updated else None,
        },
    )
    state["engagement_summary"] = summary
    return state


