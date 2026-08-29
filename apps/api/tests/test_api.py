from collections.abc import Iterator, Sequence

import pytest
from fastapi.testclient import TestClient

from glia.api import get_token_broker
from glia.config import get_settings
from glia.contracts import RealtimeTokenResponse
from glia.main import app


@pytest.fixture
def fixture_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin `demo_mode` for the tests that assert the deterministic distiller.

    Settings are read from the ambient `.env`, so without this a developer flipping `DEMO_MODE`
    to `live` turns a green suite red — the socket falls back to the local projector when
    Pioneer is unreachable, which is correct behaviour and a misleading test failure.
    """
    monkeypatch.setenv("DEMO_MODE", "fixture")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeTokenBroker:
    async def mint(self, client_id: str, languages: Sequence[str]) -> RealtimeTokenResponse:
        assert client_id == "browser-client-1"
        assert list(languages) == ["en", "es"]
        return RealtimeTokenResponse(
            value="ephemeral-test-token",
            expires_at=1_900_000_000,
            model="gpt-live-transcribe",
        )


def test_health_is_available_without_provider_keys() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_realtime_token_uses_short_lived_broker_contract() -> None:
    app.dependency_overrides[get_token_broker] = lambda: FakeTokenBroker()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/realtime-token",
                json={"client_id": "browser-client-1", "languages": ["en", "es"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "value": "ephemeral-test-token",
        "expires_at": 1_900_000_000,
        "model": "gpt-live-transcribe",
    }


def test_websocket_reconciles_deltas_and_returns_stable_intent(fixture_mode: None) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as socket:
        ready = socket.receive_json()
        assert ready["type"] == "session.ready"

        socket.send_json(
            {
                "type": "transcript.delta",
                "event_id": "event-1",
                "item_id": "item-1",
                "delta": "A lonely cobalt ",
            }
        )
        accepted = socket.receive_json()
        assert accepted == {
            "type": "transcript.accepted",
            "item_id": "item-1",
            "transcript": "A lonely cobalt ",
            "complete": False,
        }

        socket.send_json(
            {
                "type": "transcript.completed",
                "event_id": "event-2",
                "item_id": "item-1",
                "transcript": "A lonely cobalt observatory, cinematic and cold",
            }
        )
        completed = socket.receive_json()
        intent = socket.receive_json()

    assert completed["type"] == "transcript.accepted"
    assert completed["complete"] is True
    assert intent["type"] == "intent.updated"
    assert intent["stable"] is True
    assert intent["source"] == "fixture"
    assert intent["should_discover"] is True
    assert intent["change_reasons"] == ["initial"]
    assert intent["intent"]["moods"] == ["cold", "lonely"]
