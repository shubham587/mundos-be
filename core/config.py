from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings


load_dotenv()


class AppSettings(BaseSettings):
    # Pydantic v2 settings configuration
    
    mongo_uri: str = Field(default="mongodb://localhost:27017", alias="MONGO_URI")
    # Accept MONGO_DB_NAME (preferred) or DATABASE_NAME (legacy)
    database_name: str = Field(
        default="AI-lead-recovery",
        validation_alias=AliasChoices("MONGO_DB_NAME", "DATABASE_NAME"),
    )
    # Campaign collection used by email reply agent
    mongodb_campaign_collection: str = Field(
        default="campaigns", alias="MONGODB_CAMPAIGN_COLLECTION"
    )

    # OpenAI / LLM
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")

    # Booking + email sending
    booking_base_url: str = Field(default="", alias="BOOKING_BASE_URL")
    email_from_address: str = Field(
        default="noreply@clinic.example.com", alias="EMAIL_FROM_ADDRESS"
    )

    # Gmail / Google OAuth related
    google_client_secrets_file: str = Field(
        default="confidential.json", alias="GOOGLE_CLIENT_SECRETS_FILE"
    )
    google_token_file: str = Field(default="token.json", alias="GOOGLE_TOKEN_FILE")
    gmail_user_email: Optional[str] = Field(default=None, alias="GMAIL_USER_EMAIL")
    gmail_topic_name: Optional[str] = Field(default=None, alias="GMAIL_TOPIC_NAME")
    gmail_label_ids_default: str = Field(default="INBOX", alias="GMAIL_LABEL_IDS")
    gmail_label_filter_action_default: str = Field(
        default="include", alias="GMAIL_LABEL_FILTER_ACTION"
    )
    gmail_process_replies_only: bool = Field(
        default=False, alias="GMAIL_PROCESS_REPLIES_ONLY"
    )

    # Pub/Sub push security
    pubsub_verification_token: Optional[str] = Field(
        default=None, alias="PUBSUB_VERIFICATION_TOKEN"
    )
    pubsub_oidc_audience: Optional[str] = Field(
        default=None, alias="PUBSUB_OIDC_AUDIENCE"
    )

    # Auth / JWT
    jwt_secret_key: str = Field(default="dev-secret", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )

    environment: Literal["development", "production", "test"] = Field(
        default="development", alias="ENVIRONMENT"
    )

    # Twilio / booking settings (kept for other endpoints)
    twilio_account_sid: str | None = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(default=None, alias="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str | None = Field(default=None, alias="TWILIO_PHONE_NUMBER")


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


settings = get_settings()

