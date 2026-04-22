"""Application settings loaded from environment variables."""
from __future__ import annotations

import logging
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # Security
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7
    PLATFORM_ENCRYPTION_KEY: str

    # Deployment
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    BACKEND_ORIGIN: str = "http://localhost:8000"
    ENVIRONMENT: Literal["dev", "staging", "prod"] = "dev"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # LLM (Groq) — required from Phase 4
    GROQ_API_KEY: str = ""
    GROQ_MODEL_FAST: str = "llama-3.1-8b-instant"
    GROQ_MODEL_SMART: str = "llama-3.3-70b-versatile"

    # Embeddings — required from Phase 3
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DEVICE: Literal["cpu", "cuda"] = "cpu"

    # Stripe — required from Phase 5
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_SUCCESS_URL: str = ""
    STRIPE_CANCEL_URL: str = ""

    # Vapi — required from Phase 6
    VAPI_PRIVATE_KEY: str = ""
    VAPI_PUBLIC_KEY: str = ""
    VAPI_WEBHOOK_SECRET: str = ""
    VAPI_ASSISTANT_ID_DEFAULT: str = ""

    # Email (Resend) — required from Phase 5
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "onboarding@resend.dev"
    RESEND_REPLY_TO: str = ""

    # Supabase Storage — required from Phase 2
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "business-assets"

    # Scheduler
    SCHEDULER_ENABLED: bool = True


settings = Settings()

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
