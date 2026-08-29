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
    #: Shared low-latency synthesis model for live directions and the final generation prompt.
    openai_synthesis_model: str = "gpt-5.6-luna"
    openai_synthesis_timeout_seconds: float = Field(default=4.0, gt=0, le=8)
    openai_synthesis_cache_size: int = Field(default=128, ge=1, le=1_000)
    openai_realtime_token_ttl: int = Field(default=600, ge=10, le=7200)
    openai_request_timeout_seconds: float = Field(default=8.0, gt=0, le=30)

    pioneer_api_key: SecretStr | None = None
    pioneer_base_url: str = "https://api.pioneer.ai"
    pioneer_distill_model: str = "b520c775-127f-4db6-922c-da63b82b5020"
    pioneer_request_timeout_seconds: float = Field(default=15.0, gt=0, le=15)
    pioneer_max_retries: int = Field(default=1, ge=0, le=3)
    pioneer_inference_threshold: float = Field(default=0.3, ge=0, le=1)
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

    api_base_url: str = "http://localhost:8000"

    openverse_client_id: SecretStr | None = None
    openverse_client_secret: SecretStr | None = None
    openverse_base_url: str = "https://api.openverse.org"
    commons_api_url: str = "https://commons.wikimedia.org/w/api.php"

    discovery_page_size: int = Field(default=20, ge=1, le=50)
    discovery_lane_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    discovery_max_retries: int = Field(default=1, ge=0, le=3)
    discovery_debounce_ms: int = Field(default=600, ge=0, le=10_000)
    discovery_min_edge: int = Field(default=200, ge=1, le=4_000)
    discovery_max_candidates: int = Field(default=30, ge=1, le=100)
    discovery_wave_size: int = Field(default=8, ge=1, le=50)
    discovery_wave_delay_seconds: float = Field(default=0.12, ge=0, le=2)
    discovery_lane_stagger_seconds: float = Field(default=0.5, ge=0, le=5)
    discovery_lane_min_results: int = Field(default=8, ge=1, le=50)
    discovery_lane_max_attempts: int = Field(default=3, ge=1, le=4)
    discovery_cache_size: int = Field(default=64, ge=1, le=1_000)

    image_fetch_user_agent: str = "glia/0.1 (+https://github.com/glia/glia)"
    image_fetch_max_bytes: int = Field(default=5_242_880, ge=1_024, le=25_000_000)
    image_fetch_connect_timeout: float = Field(default=3.0, gt=0, le=30)
    image_fetch_total_timeout: float = Field(default=8.0, gt=0, le=60)
    image_host_allowlist: tuple[str, ...] = (
        "upload.wikimedia.org",
        "commons.wikimedia.org",
        "staticflickr.com",
        "api.openverse.org",
    )

    # fal. Two models, chosen by whether any pin carries a URL fal can actually fetch. Defaults
    # mirror `.env.example` exactly — the local `.env` already sets all four, and a default that
    # contradicted it would make the demo depend on which file won.
    fal_key: SecretStr | None = None
    fal_queue_base_url: str = "https://queue.fal.run"
    #: Where reference bytes are uploaded before a model is given a URL. Separate host from the
    #: queue: `rest.fal.ai` serves storage, `queue.fal.run` serves generation.
    fal_rest_base_url: str = "https://rest.fal.ai"
    fal_reference_model: str = "fal-ai/flux-pro/kontext/max/multi"
    fal_fallback_model: str = "fal-ai/flux/schnell"
    fal_max_reference_images: int = Field(default=4, ge=1, le=8)
    fal_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    fal_request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    #: The whole submit-and-poll budget. Past this the route returns a typed timeout rather than
    #: holding a request open; the generation may still complete upstream and is still billed.
    fal_poll_timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    fal_poll_interval_seconds: float = Field(default=1.0, gt=0, le=10)
    #: The whole fetch-and-upload budget for **one** reference. Per reference rather than per
    #: batch on purpose: a slow origin host should cost that pin, not the ones already in
    #: flight beside it.
    fal_reference_timeout_seconds: float = Field(default=20.0, gt=0, le=60)
    fal_upload_timeout_seconds: float = Field(default=20.0, gt=0, le=120)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
