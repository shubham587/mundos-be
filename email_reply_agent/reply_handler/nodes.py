from __future__ import annotations

import uuid
from typing import Any, Dict, Optional
import logging

from bson import ObjectId
from langchain_openai import ChatOpenAI

from core.config import settings
from .repository import (
    find_patient_by_email,
    find_latest_campaign_by_patient_id,
    ensure_campaign_thread_id,
    set_campaign_form_sent,
    set_campaign_declined,
    insert_interaction,
    fetch_interactions_for_campaign,
    update_engagement_summary,
    set_campaign_re_engaged
)
from .prompts import INTENT_CLASSIFIER_PROMPT, ALLOWED_INTENTS
from .prompts import KB_QA_PROMPT, KB_TEXT
from .sender_gmail import send_gmail_message

logger = logging.getLogger("email_reply_agent.reply_handler.nodes")


def load_patient_and_campaign(state: Dict[str, Any]) -> Dict[str, Any]:
    thread_id = state.get("thread_id")
    patient_email = state.get("patient_email")

    # Begin diagnostics
    try:
        logger.info(
            "agent.node.load_patient_and_campaign.begin",
            extra={
                "thread_id": thread_id,
                "patient_email": patient_email,
                "db": settings.database_name,
                "campaign_collection": settings.mongodb_campaign_collection,
            },
        )
    except Exception:
        pass

    patient = find_patient_by_email(patient_email) if patient_email else None
    state["patient_id"] = patient.get("_id") if patient else None

    campaign = None
    if state.get("patient_id"):
        campaign = find_latest_campaign_by_patient_id(state["patient_id"])
        if campaign and thread_id:
            ensure_campaign_thread_id(campaign["_id"], thread_id)
    # End diagnostics
    try:
        logger.info(
            "agent.node.load_patient_and_campaign.end",
            extra={
                "thread_id": thread_id,
                "patient_email": patient_email,
                "patient_found": bool(patient),
                "patient_id": str(state.get("patient_id")) if state.get("patient_id") else None,
                "campaign_found": bool(campaign),
                "campaign_id": str((campaign or {}).get("_id")) if campaign else None,
                "campaign_type": (campaign or {}).get("campaign_type") if campaign else None,
                "campaign_has_thread": bool(((campaign or {}).get("channel") or {}).get("thread_id")) if campaign else False,
                "would_update_thread": bool(campaign and thread_id),
            },
        )
    except Exception:
        pass

    state["campaign"] = campaign or {}
    return state


def analyze_incoming(state: Dict[str, Any]) -> Dict[str, Any]:
    reply_body: str = state.get("reply_email_body", "")
    if not reply_body:
        raise ValueError("reply_email_body is required in state")

    if not settings.openai_api_key:
        lower = reply_body.lower()
        intent = "question"
        if any(k in lower for k in ["book", "schedule", "appointment", "time slot"]):
            intent = "booking_request"
        elif any(k in lower for k in ["no", "not interested", "stop", "unsubscribe"]):
            intent = "service_denial"
        elif any(k in lower for k in ["what", "how", "when", "?"]):
            intent = "question"
        else:
            intent = "irrelevant_confused"
        sentiment = "neutral"
        state["classified_intent"] = intent
        state["incoming_sentiment"] = sentiment
        return state

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    intent_prompt = INTENT_CLASSIFIER_PROMPT.format(reply_email_body=reply_body)
    intent_resp = llm.invoke(intent_prompt)
    intent_text = intent_resp.content.strip().lower()
    state["classified_intent"] = intent_text if intent_text in ALLOWED_INTENTS else "question"

    # simple sentiment prompt
    sent = llm.invoke(f"Classify sentiment of this text as positive, neutral, or negative: {reply_body}")
    state["incoming_sentiment"] = sent.content.strip().lower()
    return state


def generate_booking_email(state: Dict[str, Any]) -> Dict[str, Any]:
    link = f"{settings.booking_base_url}"
    patient_name = (
        state.get("campaign", {}).get("patient", {}).get("name")
        or state.get("campaign", {}).get("patient_name")
        or state.get("patient_name")
        or "there"
    )
    email_content = (
        f"Hi {patient_name},\n\n"
        f"Thanks for your reply. You can choose a convenient time using the link below:\n"
        f"{link}\n\n"
        f"If you have any questions, just reply to this email.\n\n"
        f"Best,\nBright Smile Clinic Team"
        f"Contact us at +55 (11) 4567-8910"
    )
    state["booking_link"] = link
    state["email_content"] = email_content
    # Preserve threading-friendly subject: use Re: <inbound subject> if available
    inbound_subject = state.get("inbound_subject")
    subject = f"Re: {inbound_subject}" if inbound_subject and not inbound_subject.lower().startswith("re:") else (inbound_subject or "Schedule your appointment")
    state["subject"] = subject
    return state


def generate_disambiguation_email(state: Dict[str, Any]) -> Dict[str, Any]:
    patient_name = (
        state.get("campaign", {}).get("patient", {}).get("name")
        or state.get("campaign", {}).get("patient_name")
        or state.get("patient_name")
        or "there"
    )
    # Static template per spec with hardcoded helpline
    body = (
        f"Hello {patient_name},\n\n"
        "Thank you for your reply. I was unable to understand your message clearly.\n"
        "To ensure you get the help you need, please feel free to call our patient helpline directly at +91 27017 35235.\n"
        "Our team there will be happy to assist you.\n\n"
        "Thank you."
    )
    inbound_subject = state.get("inbound_subject")
    subject = (
        f"Re: {inbound_subject}" if inbound_subject and not inbound_subject.lower().startswith("re:") else (inbound_subject or "Quick clarification")
    )
    state["email_content"] = body
    state["subject"] = subject
    return state


def generate_declined_email(state: Dict[str, Any]) -> Dict[str, Any]:
    patient_name = (
        state.get("campaign", {}).get("patient", {}).get("name")
        or state.get("campaign", {}).get("patient_name")
        or state.get("patient_name")
        or "there"
    )
    body = (
        f"Hello {patient_name},\n\n"
        "We have received your message. You will not receive any further automated communications from us for this campaign.\n"
        "We wish you all the best."
    )
    inbound_subject = state.get("inbound_subject")
    subject = (
        f"Re: {inbound_subject}" if inbound_subject and not inbound_subject.lower().startswith("re:") else (inbound_subject or "Confirmation")
    )
    state["email_content"] = body
    state["subject"] = subject
    return state

## generate_clarify_email was reverted per request


def record_incoming_interaction(state: Dict[str, Any]) -> Dict[str, Any]:
    campaign = state.get("campaign", {})
    campaign_id: Optional[ObjectId] = campaign.get("_id")
    if campaign_id:
        insert_interaction(
            campaign_id=campaign_id,
            direction="incoming",
            content=state.get("reply_email_body", ""),
            intent=state.get("classified_intent"),
            sentiment=state.get("incoming_sentiment"),
        )
    return state


def update_campaign_to_declined(state: Dict[str, Any]) -> Dict[str, Any]:
    campaign = state.get("campaign", {})
    campaign_id: Optional[ObjectId] = campaign.get("_id")
    if campaign_id:
        set_campaign_declined(campaign_id)
    return state


def send_reply_email(state: Dict[str, Any]) -> Dict[str, Any]:
    campaign = state.get("campaign", {})
    to_email = (
        campaign.get("patient", {}).get("email")
        or campaign.get("patient_email")
        or campaign.get("email")
        or state.get("patient_email")
    )
    if not to_email:
        raise ValueError("Patient email not found in campaign document or state")

    # Build References chain if available: append current inbound Message-Id to existing chain
    inbound_refs = state.get("inbound_references")
    inbound_msgid = state.get("message_id")
    references = None
    if inbound_refs and inbound_msgid:
        references = f"{inbound_refs} {inbound_msgid}"
    else:
        references = inbound_refs or inbound_msgid

    resp = send_gmail_message(
        to_email=to_email,
        subject=state.get("subject", ""),
        body_text=state.get("email_content", ""),
        thread_id=state.get("thread_id"),
        in_reply_to=state.get("message_id"),
        references=references,
        from_email=None,  # let Gmail set From of the authorized account for best threading
    )
    print("---email sent---")
    state["send_result"] = {
        "status": "sent",
        "to": to_email,
        "subject": state.get("subject", ""),
        "gmail_message_id": resp.get("id"),
        "thread_id": resp.get("threadId"),
    }
    # Ensure state thread_id is aligned to Gmail response
    if resp.get("threadId"):
        state["thread_id"] = resp.get("threadId")
    return state


def analyze_outgoing(state: Dict[str, Any]) -> Dict[str, Any]:
    body = state.get("email_content", "")
    if not body:
        return state
    if not settings.openai_api_key:
        state["outgoing_sentiment"] = "neutral"
        state["outgoing_intent"] = state.get("classified_intent")
        return state
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    sent = llm.invoke(f"Classify sentiment of this text as positive, neutral, or negative: {body}")
    state["outgoing_sentiment"] = sent.content.strip().lower()
    state["outgoing_intent"] = state.get("classified_intent")
    return state


def record_outgoing_interaction(state: Dict[str, Any]) -> Dict[str, Any]:
    campaign = state.get("campaign", {})
    campaign_id: Optional[ObjectId] = campaign.get("_id")
    if campaign_id:
        insert_interaction(
            campaign_id=campaign_id,
            direction="outgoing",
            content=state.get("email_content", ""),
            intent=state.get("outgoing_intent"),
            sentiment=state.get("outgoing_sentiment"),
        )
    return state


def update_campaign_status(state: Dict[str, Any]) -> Dict[str, Any]:
    campaign = state.get("campaign", {})
    campaign_id: Optional[ObjectId] = campaign.get("_id")
    thread_id = state.get("thread_id")
    link = state.get("booking_link")
    if campaign_id and thread_id and link:
        set_campaign_form_sent(campaign_id, link, thread_id)
    return state


def ai_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    campaign = state.get("campaign", {})
    campaign_id: Optional[ObjectId] = campaign.get("_id")
    if not campaign_id:
        return state

    interactions = fetch_interactions_for_campaign(campaign_id)
    if not interactions:
        return state

    history_lines = [
        f"{i['timestamp'].isoformat()} | {i['direction']}: {i['content']}" for i in interactions
    ]
    history = "\n".join(history_lines)
    format_spec = (
        "Overall Summary-\n"
        "<one-paragraph overall summary>\n\n"
        "Chatwise Summary-\n\n"
        "<timestamp iso>: <short summary of message 1>\n\n"
        "<timestamp iso>: <short summary of message 2>\n\n"
        "..."
    )
    prompt = (
        "You are an analyst. Read the conversation history below (each line is 'ISO_TIMESTAMP | direction: content').\n"
        "Produce a concise analytical summary in EXACTLY this format (no extra text):\n\n"
        f"{format_spec}\n\n"
        f"Conversation History:\n{history}"
    )

    if not settings.openai_api_key:
        summary_text = history_lines[-1] if history_lines else ""
    else:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        resp = llm.invoke(prompt)
        summary_text = resp.content

    update_engagement_summary(campaign_id, summary_text)
    return state


# Question branch nodes
def query_knowledge_base(state: Dict[str, Any]) -> Dict[str, Any]:
    question = state.get("reply_email_body", "").strip()
    if not question:
        state["kb_answer"] = "NO_ANSWER"
        return state
    if not settings.openai_api_key:
        # Fallback: naive match within KB text
        lowered = question.lower()
        if any(k in lowered for k in ["implant", "implante"]):
            snippet = "Dental implants are a permanent solution for missing teeth; they look, feel, and function like natural teeth."
            state["kb_answer"] = snippet
            return state
        state["kb_answer"] = "NO_ANSWER"
        return state
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    prompt = KB_QA_PROMPT.format(knowledge_base_text=KB_TEXT, patient_question=question)
    resp = llm.invoke(prompt)
    answer = (resp.content or "").strip()
    state["kb_answer"] = answer if answer else "NO_ANSWER"
    return state


def generate_answer_email(state: Dict[str, Any]) -> Dict[str, Any]:
    answer = state.get("kb_answer", "NO_ANSWER")
    patient_name = (
        state.get("campaign", {}).get("patient", {}).get("name")
        or state.get("campaign", {}).get("patient_name")
        or state.get("patient_name")
        or "there"
    )
    body = (
        f"Hello {patient_name},\n\n"
        "Thank you for your question. Here is the information you requested:\n\n"
        f"{answer}\n\n"
        "If anything is unclear, feel free to reply to this email."
    )
    inbound_subject = state.get("inbound_subject")
    subject = (
        f"Re: {inbound_subject}" if inbound_subject and not inbound_subject.lower().startswith("re:") else (inbound_subject or "Your question")
    )
    state["email_content"] = body
    state["subject"] = subject

    return state


def update_campaign_for_handoff(state: Dict[str, Any]) -> Dict[str, Any]:
    campaign = state.get("campaign", {})
    campaign_id: Optional[ObjectId] = campaign.get("_id")
    if campaign_id:
        from .db import set_campaign_handoff_required
        set_campaign_handoff_required(campaign_id)
    return state


def generate_handoff_email(state: Dict[str, Any]) -> Dict[str, Any]:
    patient_name = (
        state.get("campaign", {}).get("patient", {}).get("name")
        or state.get("campaign", {}).get("patient_name")
        or state.get("patient_name")
        or "there"
    )
    body = (
        f"Hello {patient_name},\n\n"
        "Thank you for your question. Our team will review it and get back to you shortly."
    )
    inbound_subject = state.get("inbound_subject")
    subject = (
        f"Re: {inbound_subject}" if inbound_subject and not inbound_subject.lower().startswith("re:") else (inbound_subject or "We will get back to you")
    )
    state["email_content"] = body
    state["subject"] = subject
    return state


def update_campaign_re_engaged(state: Dict[str, Any]) -> Dict[str, Any]:
    campaign = state.get("campaign", {})
    campaign_id: Optional[ObjectId] = campaign.get("_id")
    if campaign_id:
        set_campaign_re_engaged(campaign_id)
    return state