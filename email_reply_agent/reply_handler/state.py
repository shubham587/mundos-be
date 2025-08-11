from __future__ import annotations

from typing import Any, Dict, TypedDict


class ReplyState(TypedDict, total=False):
    thread_id: str
    reply_email_body: str

    # Optional fallbacks from the request
    patient_email: str
    patient_name: str
    message_id: str
    inbound_subject: str
    inbound_references: str

    # Resolved entities
    patient_id: str
    campaign: Dict[str, Any]

    # Classification
    classified_intent: str
    incoming_sentiment: str
    outgoing_sentiment: str
    outgoing_intent: str

    # Booking branch
    booking_link: str
    email_content: str
    subject: str
    send_result: Dict[str, Any]

    # Question branch
    kb_answer: str
