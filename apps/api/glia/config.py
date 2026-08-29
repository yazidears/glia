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

    pioneer_api_key: SecretStr | None = None
    pioneer_base_url: str = "https://api.pioneer.ai"
    pioneer_distill_model: str = "fastino/gliner2-multi-v1"
    pioneer_request_timeout_seconds: float = Field(default=15.0, gt=0, le=15)
    pioneer_max_retries: int = Field(default=1, ge=0, le=3)
    pioneer_inference_threshold: float = Field(default=0.5, ge=0, le=1)
    distill_gate_jaccard_threshold: float = Field(default=0.4, ge=0, le=1)

    realtime_debounce_ms: int = Field(default=200, ge=50, le=2_000)
    realtime_max_message_bytes: int = Field(default=64_000, ge=1_024, le=1_000_000)

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
