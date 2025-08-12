from __future__ import annotations

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from bson import ObjectId
from dotenv import load_dotenv, find_dotenv

from agent.db import get_db
from agent.services import EmailService, LLMService
from zoneinfo import ZoneInfo
import os

load_dotenv(find_dotenv(), override=True)


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

    clinic_name = os.getenv("CLINIC_NAME", "Bright Smile Clinic")
    phone_number = "+55 (11) 4567-8910"
    patient_name = patient.get("name") or "Patient"
    clinic_website = os.getenv("CLINIC_WEBSITE", "https://brightsmileclinic.com")

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
        local_dt_obj: Optional[datetime] = None
        doctor_name_value: Optional[str] = None
        # Prefer appointment_date from appointments collection for precise date/time
        try:
            db = get_db()
            raw_cid = campaign.get("_id")
            cid = raw_cid if isinstance(raw_cid, ObjectId) else ObjectId(str(raw_cid))
            appt = db.appointments.find_one({"campaign_id": cid})
            appt_dt = appt.get("appointment_date") if appt else None
            doctor_name_value = (appt or {}).get("consulting_doctor")
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
                local_dt = appt_dt.replace(tzinfo=_Z("UTC")).astimezone(tz)
                local_dt_obj = local_dt
                local_dt_str = local_dt.strftime("%a, %d %b %Y %I:%M %p %Z")
        except Exception:
            # Fallback to next_attempt_at if appointment not found
            try:
                if isinstance(next_attempt_at, datetime):
                    from zoneinfo import ZoneInfo as _Z
                    local_dt = next_attempt_at.replace(tzinfo=_Z("UTC")).astimezone(tz)
                    local_dt_obj = local_dt
                    local_dt_str = local_dt.strftime("%a, %d %b %Y %I:%M %p %Z")
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
        # body = llm.generate_appointment_reminder_message(
        #     patient_name=patient["name"], appointment_dt_local_str=local_dt_str
        # )
        

        # start from here
        
        doctor_name = doctor_name_value or os.getenv("CONSULTING_DOCTOR", "Dr. John Doe")
        if local_dt_obj is not None:
            day_of_week = local_dt_obj.strftime("%A")
            appt_date_str = local_dt_obj.strftime("%B %d, %Y")
            appt_time_str = local_dt_obj.strftime("%I:%M %p %Z")
        else:
            day_of_week = ""
            appt_date_str = ""
            appt_time_str = ""

        body = (
            f"Dear {patient_name},\n\n"
            f"This is a friendly reminder about your scheduled appointment at {clinic_name}.\n\n"
            "We have you scheduled for:\n"
            f"{day_of_week}, {appt_date_str} at {appt_time_str}\n\n"
            f"Your appointment will be with Dr. {doctor_name} at our clinic.\n\n"
            "We look forward to seeing you.\n\n"
            "Sincerely,\n"
            f"The Team at {clinic_name}\n"
            f"Contact us at {phone_number}"
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

        if status_value  in ["RE_ENGAGED", "BOOKING_INITIATED"]:
            body = llm.generate_campaign_message(
            patient_name=patient["name"],
            campaign_type=campaign_type_value,
            attempts_made=attempts_made,
            service_name=service_name_value,
            ai_summary=ai_summary_text,
        )
        elif status_value == "HANDOFF_REQUIRED":
            state["skip"] = True
            return state
        else:
           
            if attempts_made ==0:
                subject = f"Regarding your inquiry at {clinic_name}"
                body = (
                    f"Hi {patient_name},\n\n"
                    f"Just a friendly follow-up from our team at {clinic_name}.\n\n"
                    "Our records show you reached out to us. I wanted to check in and see if this is still on your mind "
                    "or if you had any questions we could help answer.\n\n"
                    "No pressure at all, just wanted to make sure we didn't leave you hanging!\n\n"
                    "Best,\n\n"
                    f"The {clinic_name} Team\n"
                    "Contact us at +55 (11) 4567-8910"
                )
            elif attempts_made == 1:
                body = (
                    f"Hi {patient_name},\n\n"
                    "Hope you're having a great week.\n\n"
                    "I'm sending a quick, gentle follow-up to my last email. We know that life can get busy, and finding time for appointments can be tricky.\n\n"
                    "I wanted to let you know that we offer flexible scheduling, including early morning and evening slots, "
                    "to make it easier to find a time that works for you.\n\n"
                    "If you have even a small question, feel free to just reply to this email. We're happy to help.\n\n"
                    "Sincerely,\n\n"
                    f"The {clinic_name} Team\n"
                    "Contact us at +55 (11) 4567-8910"
                )
                
            else:
                body = (
                    f"Hi {patient_name},\n\n"
                    "Since I haven't heard back, I'll assume that now might not be the right time for you, "
                    "and that's completely okay. I won't reach out about this again to respect your inbox.\n\n"
                    "Please know our door is always open if you decide to move forward in the future.\n\n"
                    "Wishing you all the best.\n\n"
                    "Best regards,\n\n"
                    f"The {clinic_name} Team\n"
                    "Contact us at +55 (11) 4567-8910"
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



def node_call_patient(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("skip"):
        return state

    # Get patient phone number
    patient = state.get("patient") or {}
    phone: str = patient.get("phone", "")
    campaign = state.get("campaign") or {}

    import requests
    response = requests.post(
    "https://api.vapi.ai/call",
    headers={
        "Authorization": "Bearer 4eba9164-bf9b-49e3-966b-286aa6d83490"
    },
    json={
        "workflowId": os.getenv("WORKFLOW_ID", "6131edd5-ba16-4746-ac6a-15739bccb9e5"),
        "phoneNumberId": os.getenv("PHONE_NUMBER_ID", "7eb0770f-4067-45b6-93a9-1b71805937b7"),
        "customer": {
        "number": phone,
        "name": patient.get("name", ""),
        # "email": patient.get("email", "")
        },
        "workflowOverrides": {
        "variableValues": {"name": patient.get("name", ""),
        "service_name": campaign.get("service_name", "")}
        }
    },
    )
    

    # Static call result per requirement
    service_name_value: str = campaign.get("service_name") or "service"
    result_text = f"calling done to patient on {service_name_value}"
    state["call_result"] = result_text

    # Log interaction
    db = get_db()
    ins = db.interactions.insert_one(
        {
            "campaign_id": ObjectId(state["campaign"]["_id"]),
            "direction": "outgoing",
            "content": result_text,
            "timestamp": datetime.utcnow(),
        }
    )
    print(
        "[NODE:CALL_PATIENT] Logged interaction:",
        {"interaction_id": str(ins.inserted_id), "campaign_id": str(state["campaign"]["_id"])},
    )
    return state
