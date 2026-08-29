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
    #: The synthesis call at Generate. One ordinary chat completion, not the realtime model.
    openai_synthesis_model: str = "gpt-5.5"
    openai_realtime_token_ttl: int = Field(default=600, ge=10, le=7200)
    openai_request_timeout_seconds: float = Field(default=8.0, gt=0, le=30)

    pioneer_api_key: SecretStr | None = None
    pioneer_base_url: str = "https://api.pioneer.ai"
    pioneer_distill_model: str = "fastino/gliner2-multi-v1"
    pioneer_request_timeout_seconds: float = Field(default=15.0, gt=0, le=15)
    pioneer_max_retries: int = Field(default=1, ge=0, le=3)
    pioneer_inference_threshold: float = Field(default=0.5, ge=0, le=1)
    distill_gate_jaccard_threshold: float = Field(default=0.4, ge=0, le=1)

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
    # Connect is fast and 10s is generous. Read is not: a cold `knowledge/search` was measured
    # at 45.7s against the live API on 29 Aug 2026, and the credit is spent whether or not we
    # wait for the answer — so a short read timeout buys nothing and throws away what we paid
    # for. Measured, not guessed; see the spike note in cala.py.
    cala_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    cala_request_timeout_seconds: float = Field(default=90.0, gt=0, le=300)
    cala_entity_limit: int = Field(default=5, ge=1, le=100)

    # fal. Two models, chosen by whether any pin carries a URL fal can actually fetch. Defaults
    # mirror `.env.example` exactly — the local `.env` already sets all four, and a default that
    # contradicted it would make the demo depend on which file won.
    fal_key: SecretStr | None = None
    fal_queue_base_url: str = "https://queue.fal.run"
    fal_reference_model: str = "fal-ai/flux-pro/kontext/max/multi"
    fal_fallback_model: str = "fal-ai/flux/schnell"
    fal_max_reference_images: int = Field(default=4, ge=1, le=8)
    fal_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    fal_request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    #: The whole submit-and-poll budget. Past this the route returns a typed timeout rather than
    #: holding a request open; the generation may still complete upstream and is still billed.
    fal_poll_timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    fal_poll_interval_seconds: float = Field(default=1.0, gt=0, le=10)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
