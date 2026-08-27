from functools import lru_cache
from typing import Literal
from uuid import UUID
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RecoverAI"

    app_env: Literal[
        "development",
        "test",
        "demo",
    ] = "development"

    app_debug: bool = False

    frontend_origin: str = (
        "http://localhost:5173"
    )
    backend_api_base_url: str = (
        "http://127.0.0.1:8000/api/v1"
    )

    demo_tenant_id: UUID | None = None

    database_url: str
    redis_url: str

    # Razorpay is deliberately restricted to Test Mode.
    razorpay_mode: Literal["test"] = "test"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Real provider actions remain disabled unless
    # explicitly enabled.
    razorpay_actions_enabled: bool = False

    razorpay_api_timeout_seconds: float = 20.0

    razorpay_payment_link_expiry_minutes: int = (
        1440
    )

    # Webhook fallback reconciliation.
    razorpay_reconciliation_enabled: bool = True

    # First provider status check after creating a link.
    razorpay_reconciliation_initial_delay_seconds: int = (
        30
    )

    # Delay between provider status checks.
    razorpay_reconciliation_retry_delay_seconds: int = (
        60
    )

    # Includes the first check and all retries.
    razorpay_reconciliation_max_attempts: int = 10

    # Ollama shadow evaluation.
    ai_shadow_mode_enabled: bool = True

    ollama_base_url: str = (
        "http://127.0.0.1:11434"
    )

    ollama_model: str = "llama3:latest"

    ollama_timeout_seconds: float = 120.0

    ollama_prompt_version: str = "shadow_v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()