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

    # Cala. `CALA_CREDIT_BUDGET` is a hard ceiling, not a target: the process refuses to call
    # Cala once the ledger reaches it. 1 credit = 1 query and the pool is monthly, so the
    # honest failure is a typed refusal rather than an overdraft nobody notices until the demo.
    cala_api_key: SecretStr | None = None
    cala_base_url: str = "https://api.cala.ai/v1"
    cala_min_seconds_between_queries: float = Field(default=8.0, ge=0, le=600)
    cala_credit_budget: int = Field(default=1_100, ge=0)
    cala_cache_ttl_seconds: float = Field(default=3_600.0, gt=0)
    cala_request_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    cala_entity_limit: int = Field(default=5, ge=1, le=100)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
