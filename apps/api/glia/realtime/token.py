import asyncio
import hashlib
from collections.abc import Sequence
from typing import Protocol

from openai import OpenAI

from glia.config import Settings
from glia.contracts import RealtimeTokenResponse


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
            client = OpenAI(
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
                                "delay": "low",
                                "prompt": (
                                    "A person thinking out loud about a visual idea they want "
                                    "to create. Preserve art, design, photography, colour, mood, "
                                    "composition, material, place, and proper-name vocabulary."
                                ),
                            },
                            "turn_detection": {
                                "type": "semantic_vad",
                                "eagerness": "low",
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
            raise TokenMintFailed("OpenAI token mint failed") from exc
