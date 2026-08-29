from collections.abc import Sequence
from typing import cast

import pytest
from pydantic import SecretStr
from pytest import MonkeyPatch

from glia.config import Settings
from glia.contracts import RealtimeTokenResponse
from glia.realtime import token as token_module
from glia.realtime.token import OpenAIRealtimeTokenBroker


@pytest.mark.asyncio
async def test_openai_broker_mints_a_scoped_transcription_session(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_post_client_secret(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"value": "ephemeral-value", "expires_at": 1_900_000_000}

    monkeypatch.setattr(token_module, "_post_openai_client_secret", fake_post_client_secret)
    broker = OpenAIRealtimeTokenBroker(
        Settings(
            environment="test",
            openai_api_key=SecretStr("test-key"),
            openai_realtime_token_ttl=120,
        )
    )

    result = await broker.mint("stable-browser-client", cast(Sequence[str], ["en", "es"]))

    assert result == RealtimeTokenResponse(
        value="ephemeral-value",
        expires_at=1_900_000_000,
        model="gpt-live-transcribe",
    )
    body = cast(dict[str, object], captured["body"])
    assert body["expires_after"] == {"anchor": "created_at", "seconds": 120}
    session = cast(dict[str, object], body["session"])
    assert session["type"] == "transcription"
    audio = cast(dict[str, object], session["audio"])
    audio_input = cast(dict[str, object], audio["input"])
    transcription = cast(dict[str, object], audio_input["transcription"])
    assert transcription["model"] == "gpt-live-transcribe"
    assert transcription["languages"] == ["en", "es"]
    assert "turn_detection" not in audio_input
    assert captured["api_key"] == "test-key"
    assert captured["safety_identifier"] != "stable-browser-client"
    assert "test-key" not in result.model_dump_json()
