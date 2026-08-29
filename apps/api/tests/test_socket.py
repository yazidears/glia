import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from typing import cast

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from glia.contracts import Candidate, CandidatesBatch, VisualIntent
from glia.discovery.query import build_preview_queries
from glia.discovery.service import DiscoveryService
from glia.realtime.distiller import DistillationResult
from glia.realtime.ideas import IdeaResult
from glia.realtime.socket import RealtimeSocketSession, _is_socket_shutdown


class RecordingWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send_text(self, payload: str) -> None:
        self.messages.append(json.loads(payload))


class PartialPioneerDistiller:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def distill(self, transcript: str) -> DistillationResult:
        self.calls.append(transcript)
        return DistillationResult(
            intent=VisualIntent(
                subject="",
                moods=[],
                styles=[],
                palette=["color azul"],
            ),
            source="pioneer",
        )


class RecordingIdeaSynthesizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, VisualIntent]] = []

    async def synthesize(self, transcript: str, intent: VisualIntent) -> IdeaResult:
        self.calls.append((transcript, intent))
        return IdeaResult(
            ideas=[f"Visual direction for {intent.subject}"],
            keywords=[intent.subject],
            source="local",
        )


class BlockingIdeaSynthesizer:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def synthesize(self, transcript: str, intent: VisualIntent) -> IdeaResult:
        del transcript
        self.started.set()
        await self.release.wait()
        return IdeaResult(
            ideas=[intent.subject],
            keywords=[intent.subject],
            source="openai",
            search_queries=["blue automobile product photography"],
        )


class RecordingDiscovery:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.calls: list[tuple[tuple[str, ...], int, bool]] = []

    async def discover(
        self,
        *,
        queries: Sequence[str],
        revision: int,
        emit: Callable[[CandidatesBatch], Awaitable[None]],
        include_cited: bool = True,
    ) -> list[Candidate]:
        del emit
        self.calls.append((tuple(queries), revision, include_cited))
        self.started.set()
        return []


def test_socket_shutdown_recognises_task_group_disconnects() -> None:
    wrapped = ExceptionGroup("lane failed", [WebSocketDisconnect(code=1006)])

    assert _is_socket_shutdown(wrapped)
    assert not _is_socket_shutdown(ExceptionGroup("bug", [ValueError("bad candidate")]))


@pytest.mark.asyncio
async def test_socket_deduplicates_candidate_ids_within_one_revision() -> None:
    websocket = RecordingWebSocket()
    session = RealtimeSocketSession(
        websocket=cast(WebSocket, websocket),
        debounce_ms=1,
        max_message_bytes=10_000,
        discovery=None,
    )
    candidate = Candidate(
        id="commons:observatory",
        lane="open",
        image_url="https://example.test/observatory.jpg",
        source_url="https://example.test/observatory",
        score=1.0,
    )

    await session._send(CandidatesBatch(revision=1, candidates=[candidate]))
    await session._send(CandidatesBatch(revision=1, candidates=[candidate]))
    await session._send(CandidatesBatch(revision=2, candidates=[candidate]))

    assert [message["revision"] for message in websocket.messages] == [1, 2]


@pytest.mark.asyncio
async def test_stable_projection_fills_only_empty_pioneer_fields_from_latest_turn() -> None:
    websocket = RecordingWebSocket()
    distiller = PartialPioneerDistiller()
    session = RealtimeSocketSession(
        websocket=cast(WebSocket, websocket),
        debounce_ms=1,
        max_message_bytes=10_000,
        distiller=distiller,
        discovery=None,
    )

    await session._handle(
        json.dumps(
            {
                "type": "transcript.completed",
                "event_id": "event-blue-cars",
                "item_id": "item-blue-cars",
                "transcript": "Brutalist blue observatory",
            }
        )
    )
    await session._cancel_pending_discovery()

    assert distiller.calls == ["Brutalist blue observatory"]
    update = websocket.messages[1]
    assert update["type"] == "intent.updated"
    assert update["source"] == "pioneer"
    assert update["intent"] == {
        "subject": "observatory",
        "moods": [],
        "styles": ["brutalist"],
        "palette": ["color azul"],
        "composition": "",
        "medium": "",
        "era": "",
    }


@pytest.mark.asyncio
async def test_partial_projection_uses_only_the_active_transcript_item() -> None:
    websocket = RecordingWebSocket()
    session = RealtimeSocketSession(
        websocket=cast(WebSocket, websocket),
        debounce_ms=1,
        max_message_bytes=10_000,
        distiller=PartialPioneerDistiller(),
        discovery=None,
    )

    await session._handle(
        json.dumps(
            {
                "type": "transcript.completed",
                "event_id": "event-apples",
                "item_id": "item-apples",
                "transcript": "Manzanas verdes.",
            }
        )
    )
    await session._cancel_pending_discovery()
    websocket.messages.clear()

    await session._handle(
        json.dumps(
            {
                "type": "transcript.delta",
                "event_id": "event-cats",
                "item_id": "item-cats",
                "delta": "Gatos y perros",
            }
        )
    )
    pending = session._pending_projection
    assert pending is not None
    await pending

    update = websocket.messages[1]
    assert update["type"] == "intent.updated"
    assert update["transcript"] == "Manzanas verdes. Gatos y perros"
    assert update["intent"] == {
        "subject": "gatos perros",
        "moods": [],
        "styles": [],
        "palette": [],
        "composition": "",
        "medium": "",
        "era": "",
    }


@pytest.mark.asyncio
async def test_openai_ideas_keep_full_project_context_while_fastino_uses_latest_turn() -> None:
    websocket = RecordingWebSocket()
    distiller = PartialPioneerDistiller()
    ideas = RecordingIdeaSynthesizer()
    session = RealtimeSocketSession(
        websocket=cast(WebSocket, websocket),
        debounce_ms=1,
        max_message_bytes=10_000,
        distiller=distiller,
        idea_synthesizer=ideas,
        discovery=None,
    )
    turns = [
        "Estem creant una empresa de mobilitat.",
        "El dashboard ha de mostrar cotxes blaus.",
    ]

    for index, turn in enumerate(turns):
        await session._handle(
            json.dumps(
                {
                    "type": "transcript.completed",
                    "event_id": f"context-event-{index}",
                    "item_id": f"context-item-{index}",
                    "transcript": turn,
                }
            )
        )
        pending = session._pending_discovery
        assert pending is not None
        await pending

    assert distiller.calls == turns
    assert ideas.calls[-1][0] == " ".join(turns)
    assert ideas.calls[-1][1].subject == "dashboard ui"


@pytest.mark.asyncio
async def test_settled_search_starts_fastino_queries_while_openai_refines() -> None:
    websocket = RecordingWebSocket()
    ideas = BlockingIdeaSynthesizer()
    discovery = RecordingDiscovery()
    session = RealtimeSocketSession(
        websocket=cast(WebSocket, websocket),
        debounce_ms=1,
        max_message_bytes=10_000,
        idea_synthesizer=ideas,
        discovery=cast(DiscoveryService, discovery),
        discovery_debounce_ms=0,
    )
    intent = VisualIntent(subject="cotxes", moods=[], styles=[], palette=["blau"])

    session._schedule_discovery("Vull cotxes blaus", intent)
    pending = session._pending_discovery
    assert pending is not None
    await asyncio.wait_for(ideas.started.wait(), timeout=1)
    await asyncio.wait_for(discovery.started.wait(), timeout=1)
    assert discovery.calls == [(build_preview_queries(intent), 0, False)]
    assert not any(
        message["type"] == "ideas.updated" and message["source"] == "openai"
        for message in websocket.messages
    )

    ideas.release.set()
    await pending
    assert discovery.calls[1][0][0] == "blue automobile product photography"
    assert discovery.calls[1][1:] == (0, True)
    assert any(message["type"] == "ideas.updated" for message in websocket.messages)


@pytest.mark.asyncio
async def test_full_context_semantic_preview_does_not_wait_for_openai() -> None:
    websocket = RecordingWebSocket()
    openai = BlockingIdeaSynthesizer()
    discovery = RecordingDiscovery()
    session = RealtimeSocketSession(
        websocket=cast(WebSocket, websocket),
        debounce_ms=1,
        max_message_bytes=10_000,
        idea_synthesizer=openai,
        discovery=cast(DiscoveryService, discovery),
        discovery_debounce_ms=0,
    )
    transcript = (
        "Estem creant una marca de roba mediterrània. "
        "Volem un estil relaxat. Textil tranquil."
    )
    current_intent = VisualIntent(
        subject="textil",
        moods=["tranquilo"],
        styles=[],
        palette=[],
    )

    session._schedule_discovery(transcript, current_intent)
    pending = session._pending_discovery
    assert pending is not None
    await asyncio.wait_for(openai.started.wait(), timeout=1)
    await asyncio.wait_for(discovery.started.wait(), timeout=1)

    assert discovery.calls == [
        (
            (
                "Mediterranean fashion",
                "Mediterranean clothing",
                "Mediterranean lifestyle",
            ),
            0,
            False,
        )
    ]
    assert any(
        message["type"] == "ideas.updated" and message["source"] == "local"
        for message in websocket.messages
    )
    assert not any(
        message["type"] == "ideas.updated" and message["source"] == "openai"
        for message in websocket.messages
    )

    openai.release.set()
    await pending
    assert discovery.calls[-1][1:] == (0, True)
