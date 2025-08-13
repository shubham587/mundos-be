from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def _to_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


@dataclass
class Settings:
    mongodb_uri: str = os.getenv("MONGO_URI")
    mongodb_db_name: str = os.getenv("MONGO_DB_NAME", "AI-lead-recovery")
    mongodb_campaign_collection: str = os.getenv("MONGODB_CAMPAIGN_COLLECTION", "campaigns")

    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")

    booking_base_url: str = os.getenv("BOOKING_BASE_URL", "")
    email_from_address: str = os.getenv("EMAIL_FROM_ADDRESS", "noreply@clinic.example.com")

    # Gmail / PubSub integration
    google_client_secrets_file: str = os.getenv("GOOGLE_CLIENT_SECRETS_FILE", "confidential.json")
    google_token_file: str = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
    gmail_user_email: Optional[str] = os.getenv("GMAIL_USER_EMAIL")
    gmail_topic_name: Optional[str] = os.getenv("GMAIL_TOPIC_NAME")  # projects/<project>/topics/<topic>
    gmail_label_ids_default: str = os.getenv("GMAIL_LABEL_IDS", "INBOX")
    gmail_label_filter_action_default: str = os.getenv("GMAIL_LABEL_FILTER_ACTION", "include")
    gmail_process_replies_only: bool = _to_bool(os.getenv("GMAIL_PROCESS_REPLIES_ONLY"), default=False)

    pubsub_verification_token: Optional[str] = os.getenv("PUBSUB_VERIFICATION_TOKEN")
    pubsub_oidc_audience: Optional[str] = os.getenv("PUBSUB_OIDC_AUDIENCE")


settings = Settings()
