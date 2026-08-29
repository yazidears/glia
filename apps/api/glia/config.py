from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local", "../../.env", "../../.env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "info"
    web_origin: str = "http://localhost:5173"
    demo_mode: Literal["fixture", "live"] = "fixture"

    openai_api_key: SecretStr | None = None
    openai_transcribe_model: str = "gpt-live-transcribe"
    openai_realtime_token_ttl: int = Field(default=600, ge=10, le=7200)
    openai_request_timeout_seconds: float = Field(default=8.0, gt=0, le=30)

    realtime_debounce_ms: int = Field(default=200, ge=50, le=2_000)
    realtime_max_message_bytes: int = Field(default=64_000, ge=1_024, le=1_000_000)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
