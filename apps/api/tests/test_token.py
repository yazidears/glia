from collections.abc import Sequence
from types import SimpleNamespace
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

    class FakeClientSecrets:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(value="ephemeral-value", expires_at=1_900_000_000)

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured["client"] = kwargs
            self.realtime = SimpleNamespace(client_secrets=FakeClientSecrets())

    monkeypatch.setattr(token_module, "OpenAI", FakeOpenAI)
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
    assert captured["expires_after"] == {"anchor": "created_at", "seconds": 120}
    session = cast(dict[str, object], captured["session"])
    assert session["type"] == "transcription"
    assert "test-key" not in result.model_dump_json()
