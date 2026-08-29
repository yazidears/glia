from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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
    # A lane walks up to three ladder rungs inside this one budget. Measured against the
    # live APIs on 29 Aug 2026: Commons p50 0.84s / max 1.14s per rung, Openverse p50 0.14s
    # / max 0.44s. Worst realistic walk is three Commons rungs plus one retry ≈ 5s, so 12s
    # is that plus headroom for a bad day rather than a number that felt about right.
    discovery_lane_timeout_seconds: float = Field(default=12.0, gt=0, le=60)
    # One HTTP request may not eat the whole lane budget: a rung that hangs has to give up
    # while later rungs can still run. Commons `insource:` regex queries hang past 30s.
    discovery_request_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    discovery_max_retries: int = Field(default=1, ge=0, le=3)
    # Pure dead wait in front of the first query, and it was 600ms of a 2.06s
    # time-to-first-image (measured 29 Aug 2026: 600ms here + 1361ms of lane work).
    # Coalescing rapid subject changes is its real job, and 250ms still does that —
    # `_schedule_discovery` already refuses to re-run an unchanged subject.
    discovery_debounce_ms: int = Field(default=250, ge=0, le=10_000)
    discovery_min_edge: int = Field(default=200, ge=1, le=4_000)
    discovery_max_candidates: int = Field(default=30, ge=1, le=100)
    discovery_wave_size: int = Field(default=8, ge=1, le=50)
    discovery_wave_delay_seconds: float = Field(default=0.12, ge=0, le=2)
    discovery_lane_min_results: int = Field(default=8, ge=1, le=50)
    discovery_lane_max_attempts: int = Field(default=3, ge=1, le=4)
    discovery_cache_size: int = Field(default=64, ge=1, le=1_000)

    image_fetch_user_agent: str = "glia/0.1 (+https://github.com/nectios/glia; glia@nectios.com)"
    image_fetch_max_bytes: int = Field(default=5_242_880, ge=1_024, le=25_000_000)
    image_fetch_connect_timeout: float = Field(default=3.0, gt=0, le=30)
    image_fetch_total_timeout: float = Field(default=8.0, gt=0, le=60)
    image_host_allowlist: tuple[str, ...] = (
        "upload.wikimedia.org",
        "commons.wikimedia.org",
        "staticflickr.com",
        "api.openverse.org",
    )

    @field_validator("image_fetch_user_agent")
    @classmethod
    def _reject_placeholder_user_agent(cls, value: str) -> str:
        """Refuse to start on an unfilled User-Agent template.

        Wikimedia enforces a User-Agent policy and does reject on it: a request sent as
        `python-httpx/0.28.1` is answered 403 in 0.13s (measured 29 Aug 2026). A UA still
        carrying `<org>` is not rejected *today*, but it is a template nobody filled in,
        it identifies no one, and it is exactly what the policy exists to stop. Failing at
        startup is cheaper than discovering it as a dead lane mid-demo.
        """
        if "<" in value or ">" in value:
            raise ValueError(
                "IMAGE_FETCH_USER_AGENT still contains a '<...>' placeholder. Wikimedia's "
                "User-Agent policy requires a real contact: set it to something like "
                "'glia/0.1 (+https://github.com/your-org/glia; you@example.com)'."
            )
        if not value.strip():
            raise ValueError("IMAGE_FETCH_USER_AGENT must not be empty.")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
