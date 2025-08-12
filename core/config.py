from __future__ import annotations

from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()


class AppSettings(BaseSettings):
    # Pydantic v2 settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        case_sensitive=False,
        extra="ignore",  # ignore unknown keys present in .env / environment
    )

    mongo_uri: str = Field(default="mongodb://localhost:27017", alias="MONGO_URI")
    # Accept MONGO_DB_NAME (preferred) or DATABASE_NAME (legacy)
    database_name: str = Field(
        default="AI-lead-recovery",
        validation_alias=AliasChoices("MONGO_DB_NAME", "DATABASE_NAME"),
    )

    jwt_secret_key: str = Field(default="dev-secret", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    environment: Literal["development", "production", "test"] = Field(
        default="development", alias="ENVIRONMENT"
    )

    # Twilio / booking settings
    booking_base_url: str = Field(default="", alias="BOOKING_BASE_URL")
    twilio_account_sid: str | None = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(default=None, alias="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str | None = Field(default=None, alias="TWILIO_PHONE_NUMBER")


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


settings = get_settings()

