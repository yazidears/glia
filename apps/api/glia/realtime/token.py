import asyncio
import hashlib
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from glia.config import Settings
from glia.contracts import RealtimeTokenResponse

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from openai import OpenAI


def _create_openai_client(
    *,
    api_key: str,
    timeout: float,
    max_retries: int,
    default_headers: dict[str, str],
) -> "OpenAI":
    # Import lazily so health checks and the deterministic websocket path do not
    # pay the SDK import cost. The key remains exclusively on the API process.
    from openai import OpenAI

    return OpenAI(
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
        default_headers=default_headers,
    )


class TokenBrokerUnavailable(RuntimeError):
    """Raised when live transcription has not been configured."""


class TokenMintFailed(RuntimeError):
    """Raised when OpenAI cannot mint a short-lived Realtime credential."""


class RealtimeTokenBroker(Protocol):
    async def mint(self, client_id: str, languages: Sequence[str]) -> RealtimeTokenResponse: ...


class OpenAIRealtimeTokenBroker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def mint(self, client_id: str, languages: Sequence[str]) -> RealtimeTokenResponse:
        api_key = self._settings.openai_api_key
        if api_key is None or not api_key.get_secret_value():
            raise TokenBrokerUnavailable("OPENAI_API_KEY is not configured")

        safety_identifier = hashlib.sha256(client_id.encode("utf-8")).hexdigest()

        def create_secret() -> RealtimeTokenResponse:
            client = _create_openai_client(
                api_key=api_key.get_secret_value(),
                timeout=self._settings.openai_request_timeout_seconds,
                max_retries=1,
                default_headers={"OpenAI-Safety-Identifier": safety_identifier},
            )
            secret = client.realtime.client_secrets.create(
                expires_after={
                    "anchor": "created_at",
                    "seconds": self._settings.openai_realtime_token_ttl,
                },
                session={
                    "type": "transcription",
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": 24_000},
                            "noise_reduction": {"type": "near_field"},
                            "transcription": {
                                "model": self._settings.openai_transcribe_model,
                                "languages": list(languages),
                                "keywords": [
                                    "art",
                                    "design",
                                    "photography",
                                    "colour",
                                    "mood",
                                    "composition",
                                    "material",
                                ],
                            },
                        }
                    },
                },
            )
            return RealtimeTokenResponse(
                value=secret.value,
                expires_at=secret.expires_at,
                model=self._settings.openai_transcribe_model,
            )

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(create_secret),
                timeout=self._settings.openai_request_timeout_seconds + 1,
            )
        except TimeoutError as exc:
            raise TokenMintFailed("OpenAI token mint timed out") from exc
        except TokenBrokerUnavailable:
            raise
        except Exception as exc:
            logger.warning(
                "OpenAI Realtime token mint failed: error=%s status=%s code=%s",
                type(exc).__name__,
                getattr(exc, "status_code", None),
                getattr(exc, "code", None),
            )
            raise TokenMintFailed("OpenAI token mint failed") from exc
