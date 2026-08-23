from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RecoverAI"
    app_env: Literal["development", "test", "demo"] = "development"
    app_debug: bool = False

    frontend_origin: str = "http://localhost:5173"

    database_url: str
    redis_url: str

    razorpay_mode: Literal["test"] = "test"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    
    ai_shadow_mode_enabled: bool = True
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3:latest"
    ollama_timeout_seconds: float = 120.0
    ollama_prompt_version: str = "shadow_v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()