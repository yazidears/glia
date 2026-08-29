import time
from collections.abc import Sequence

from fastapi.testclient import TestClient

from glia.api import get_token_broker
from glia.contracts import RealtimeTokenResponse
from glia.main import app


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


def test_websocket_reconciles_deltas_and_returns_stable_intent() -> None:
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


def test_websocket_streams_candidates_after_a_stable_intent() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as socket:
        assert socket.receive_json()["type"] == "session.ready"
        socket.send_json(
            {
                "type": "transcript.completed",
                "event_id": "event-1",
                "item_id": "item-1",
                "transcript": "A lonely cobalt observatory, cinematic and cold",
            }
        )
        assert socket.receive_json()["type"] == "transcript.accepted"
        intent = socket.receive_json()
        batch = socket.receive_json()

    assert intent["type"] == "intent.updated"
    assert intent["should_discover"] is True
    assert batch["type"] == "candidates.batch"
    assert batch["revision"] == intent["revision"]
    assert batch["candidates"]
    for candidate in batch["candidates"]:
        assert candidate["lane"] == "open"
        assert candidate["title"]
        assert candidate["licence"]
        assert candidate["width"] and candidate["height"]
        assert candidate["image_url"].startswith("http://localhost:8000/api/image?url=")


def test_websocket_does_not_rediscover_an_unchanged_subject() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as socket:
        socket.receive_json()
        for index, transcript in enumerate(
            ["A cobalt observatory", "A cobalt observatory, cinematic"]
        ):
            socket.send_json(
                {
                    "type": "transcript.completed",
                    "event_id": f"event-{index}",
                    "item_id": f"item-{index}",
                    "transcript": transcript,
                }
            )
        # accepted, intent, batch for the first turn; accepted, intent for the second.
        messages = [socket.receive_json() for _ in range(5)]
        # Long enough for a second discovery to have cleared its debounce.
        time.sleep(1.5)
        socket.send_json({"type": "ping", "event_id": "ping-1"})
        following = socket.receive_json()

    assert sorted(message["type"] for message in messages) == [
        "candidates.batch",
        "intent.updated",
        "intent.updated",
        "transcript.accepted",
        "transcript.accepted",
    ]
    # The second turn sharpens the intent but names the same subject, so the
    # grid is not refilled and nothing else is waiting behind the pong.
    assert following == {"type": "pong", "event_id": "ping-1"}
