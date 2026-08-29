import asyncio
import hashlib
import logging
from collections.abc import Sequence
from typing import Protocol, TypedDict

import httpx

from glia.config import Settings
from glia.contracts import RealtimeTokenResponse

logger = logging.getLogger(__name__)


class _ClientSecretPayload(TypedDict):
    value: str
    expires_at: int


async def _post_openai_client_secret(
    *,
    api_key: str,
    request_timeout_seconds: float,
    safety_identifier: str,
    body: dict[str, object],
) -> _ClientSecretPayload:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Safety-Identifier": safety_identifier,
    }
    async with httpx.AsyncClient(timeout=request_timeout_seconds) as client:
        response = await client.post(
            "https://api.openai.com/v1/realtime/client_secrets",
            headers=headers,
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("value"), str)
        or not isinstance(payload.get("expires_at"), int)
    ):
        raise ValueError("OpenAI returned an invalid client secret response")
    return {"value": payload["value"], "expires_at": payload["expires_at"]}


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

        body: dict[str, object] = {
            "expires_after": {
                "anchor": "created_at",
                "seconds": self._settings.openai_realtime_token_ttl,
            },
            "session": {
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
        }

        async def create_secret() -> RealtimeTokenResponse:
            payload = await _post_openai_client_secret(
                api_key=api_key.get_secret_value(),
                request_timeout_seconds=self._settings.openai_request_timeout_seconds,
                safety_identifier=safety_identifier,
                body=body,
            )
            return RealtimeTokenResponse(
                value=payload["value"],
                expires_at=payload["expires_at"],
                model=self._settings.openai_transcribe_model,
            )

        try:
            return await asyncio.wait_for(
                create_secret(),
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
                getattr(getattr(exc, "response", None), "status_code", None),
                getattr(exc, "code", None),
            )
            raise TokenMintFailed("OpenAI token mint failed") from exc
