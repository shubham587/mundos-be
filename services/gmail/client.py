from __future__ import annotations

import os
from typing import Any, Dict, Optional, List

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from core.config import settings


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


def load_credentials() -> Credentials:
    token_path = settings.google_token_file
    if not os.path.exists(token_path):
        raise RuntimeError(f"Google token file not found: {token_path}")
    creds = Credentials.from_authorized_user_file(token_path, scopes=GMAIL_SCOPES)
    return creds


def build_gmail_service() -> Any:
    creds = load_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return service


def start_watch(
    *,
    topic_name: str,
    label_ids: Optional[List[str]] = None,
    label_filter_action: str = "include",
    user_id: str = "me",
) -> Dict[str, Any]:
    service = build_gmail_service()
    body: Dict[str, Any] = {
        "topicName": topic_name,
        "labelFilterAction": label_filter_action,
    }
    if label_ids:
        body["labelIds"] = label_ids
    resp = service.users().watch(userId=user_id, body=body).execute()
    return resp
