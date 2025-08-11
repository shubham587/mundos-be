from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Optional

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from .config import settings


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


def _build_service():
    creds = Credentials.from_authorized_user_file(settings.google_token_file, scopes=GMAIL_SCOPES)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_gmail_message(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    from_email: Optional[str] = None,
) -> dict:
    service = _build_service()

    msg = EmailMessage()
    msg["To"] = to_email
    if from_email:
        msg["From"] = from_email
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body_text)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    body = {"raw": raw}
    if thread_id:
        body["threadId"] = thread_id

    return service.users().messages().send(userId="me", body=body).execute()
