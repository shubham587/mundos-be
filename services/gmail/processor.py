from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional
import logging
from email.utils import parseaddr

from html2text import html2text

from .client import build_gmail_service
from email_reply_agent.reply_handler.repository import get_last_history_id, set_last_history_id, has_processed_message, mark_processed_message
from email_reply_agent.reply_handler.graph import run_reply_workflow
from core.config import settings


logger = logging.getLogger("services.gmail.processor")
logger.setLevel(logging.INFO)


def _decode_pubsub_message(data_b64: str) -> Dict[str, Any]:
    decoded = base64.b64decode(data_b64)
    return json.loads(decoded)


def _get_header(headers: List[Dict[str, str]], name: str) -> Optional[str]:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def _extract_plain_text(payload: Dict[str, Any]) -> str:
    mime_type = payload.get("mimeType")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        return ""
    if mime_type == "text/html":
        data = payload.get("body", {}).get("data")
        if data:
            html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            return html2text(html)
        return ""
    parts = payload.get("parts", []) or []
    for part in parts:
        text = _extract_plain_text(part)
        if text:
            return text
    return ""


def process_pubsub_push(pubsub_body: Dict[str, Any]) -> Dict[str, Any]:
    message = pubsub_body.get("message", {})
    data_b64 = message.get("data")
    if not data_b64:
        return {"ok": False, "reason": "no_data"}

    change = _decode_pubsub_message(data_b64)
    email_address = change.get("emailAddress")
    history_id = change.get("historyId")
    if not email_address or not history_id:
        return {"ok": False, "reason": "missing_email_or_history"}

    service = build_gmail_service()

    start_history_id = get_last_history_id(email_address)
    page_token = None
    processed = 0
    max_history_seen: Optional[int] = None

    while True:
        list_kwargs: Dict[str, Any] = {
            "userId": email_address,
            "startHistoryId": start_history_id or history_id,
            "historyTypes": ["messageAdded"],
            "labelId": "INBOX",
        }
        if page_token:
            list_kwargs["pageToken"] = page_token
        hist_resp = service.users().history().list(**list_kwargs).execute()
        histories = hist_resp.get("history", [])
        for h in histories:
            try:
                hid = int(h.get("id")) if h.get("id") is not None else None
                if hid is not None:
                    max_history_seen = hid if max_history_seen is None else max(max_history_seen, hid)
            except Exception:
                pass
            for added in h.get("messagesAdded", []):
                msg_meta = added.get("message", {})
                msg_id = msg_meta.get("id")
                if not msg_id:
                    continue
                if has_processed_message(email_address, msg_id):
                    continue
                msg = service.users().messages().get(userId=email_address, id=msg_id, format="full").execute()
                label_ids = set(msg.get("labelIds", []))
                if "INBOX" not in label_ids or "SENT" in label_ids:
                    continue
                payload = msg.get("payload", {})
                headers = payload.get("headers", [])
                thread_id = msg.get("threadId")
                from_header = _get_header(headers, "From")
                # Parse printable name/email into plain email address
                from_email = parseaddr(from_header or "")[1] if from_header else None
                # Extract headers for proper threading and subject continuity
                smtp_message_id = _get_header(headers, "Message-Id") or _get_header(headers, "Message-ID")
                subject_header = _get_header(headers, "Subject")
                references_header = _get_header(headers, "References")
                if settings.gmail_process_replies_only:
                    in_reply_to = _get_header(headers, "In-Reply-To")
                    if not in_reply_to:
                        continue
                body_text = _extract_plain_text(payload)
                # Log agent invocation context (visible in terminal)
                logger.info(
                    "gmail.invoke_agent",
                    extra={
                        "thread_id": thread_id,
                        "from_email": from_email,
                        "subject": subject_header,
                        "body_len": len(body_text or ""),
                    },
                )
                result = run_reply_workflow(
                    thread_id=thread_id,
                    reply_email_body=body_text,
                    patient_email=from_email,
                    message_id=smtp_message_id,
                    inbound_subject=subject_header,
                    inbound_references=references_header,
                )
                try:
                    logger.info(
                        "gmail.agent_result",
                        extra={
                            "thread_id": result.get("thread_id") or thread_id,
                            "intent": result.get("classified_intent"),
                            "has_send_result": bool(result.get("send_result")),
                            "has_subject": bool(result.get("subject")),
                        },
                    )
                except Exception:
                    # Never let logging failures break processing
                    pass
                mark_processed_message(email_address, msg_id, thread_id)
                # Ensure visibility even if logger config filters this module
                try:
                    print(
                        f"[GMAIL] invoke_agent thread_id={thread_id} from={from_email} subject={subject_header} body_len={len(body_text or '')}",
                        flush=True,
                    )
                except Exception:
                    pass
                processed += 1
        page_token = hist_resp.get("nextPageToken")
        if not page_token:
            break

    next_checkpoint = str(max_history_seen) if max_history_seen is not None else str(history_id)
    set_last_history_id(email_address, next_checkpoint)

    return {"ok": True, "processed": processed, "emailAddress": email_address, "historyId": history_id}
