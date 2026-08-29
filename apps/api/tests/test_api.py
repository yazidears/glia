import time
from collections.abc import Sequence

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from glia.api import get_cala_client, get_discovery_service, get_token_broker
from glia.config import get_settings
from glia.contracts import CalaEntityHit, CalaSearchResult, LedgerSnapshot, RealtimeTokenResponse
from glia.discovery.service import LaneReport
from glia.main import app


class SpyCalaClient:
    """Records what the endpoint would have spent. Every upstream call is a credit."""

    configured = True

    def __init__(self) -> None:
        self.calls: list[str] = []

    class _Debounce:
        @staticmethod
        def seconds_remaining(session_id: str) -> float:
            return 0.0

        @staticmethod
        def mark(session_id: str) -> None:
            return None

    debounce = _Debounce()

    def last_reply(self, session_id: str) -> None:
        return None

    async def resolve_entity(self, subject: str) -> tuple[CalaEntityHit | None, bool]:
        self.calls.append(f"resolve_entity:{subject}")
        return None, False

    async def search(self, query: str) -> tuple[CalaSearchResult, bool]:
        self.calls.append(f"search:{query}")
        return CalaSearchResult(), False

    def remember_reply(self, session_id: str, response: object) -> None:
        return None

    def snapshot(self) -> LedgerSnapshot:
        return LedgerSnapshot(
            budget=1_100, spent=0, remaining=1_100, search_calls=0, entity_calls=0
        )


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


def test_websocket_reconciles_deltas_and_returns_stable_intent(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "fixture")
    get_settings.cache_clear()
    try:
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
    finally:
        get_settings.cache_clear()

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


def test_health_reports_every_lane_so_a_dead_lane_needs_no_log_reading() -> None:
    with TestClient(app) as client:
        body = client.get("/health").json()

    assert body["image_discovery"] is True
    assert [lane["lane"] for lane in body["lanes"]] == ["fixture"]
    assert body["lanes"][0]["status"] == "ok"
    assert body["lanes"][0]["count"] > 0


def test_health_says_images_cannot_arrive_when_every_lane_is_down() -> None:
    class DeadService:
        async def probe(self) -> list[LaneReport]:
            return [
                LaneReport(lane="commons", status="unavailable", count=0, elapsed=0.1),
                LaneReport(lane="openverse", status="timeout", count=0, elapsed=8.0),
            ]

    app.dependency_overrides[get_discovery_service] = DeadService
    try:
        with TestClient(app) as client:
            body = client.get("/health").json()
    finally:
        app.dependency_overrides.clear()

    assert body["image_discovery"] is False
    assert {lane["status"] for lane in body["lanes"]} == {"unavailable", "timeout"}


def test_a_filler_transcript_never_reaches_cala() -> None:
    """`hola hola` must cost nothing: no entity resolution, no search, no credit."""
    client_stub = SpyCalaClient()
    app.dependency_overrides[get_cala_client] = lambda: client_stub
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/discover",
                json={"transcript": "hola, hola, hola", "session_id": "s1"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "empty"
    assert client_stub.calls == []
