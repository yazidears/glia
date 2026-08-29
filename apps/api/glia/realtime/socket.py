import asyncio
import json
from contextlib import suppress
from uuid import uuid4

import structlog
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from glia.contracts import (
    CandidatesBatch,
    IdeasUpdated,
    IntentUpdated,
    Ping,
    Pong,
    ServerMessage,
    SessionReady,
    SocketError,
    TranscriptAccepted,
    TranscriptCompleted,
    TranscriptDelta,
    VisualIntent,
    client_message_adapter,
)
from glia.discovery.query import build_preview_queries, build_queries
from glia.discovery.service import DiscoveryService
from glia.realtime.distiller import (
    DiscoveryGate,
    DistillationResult,
    DistillationUnavailable,
    FixtureIntentDistiller,
    IntentDistiller,
)
from glia.realtime.ideas import (
    IdeasUnavailable,
    IdeaSynthesizer,
    LocalIdeaSynthesizer,
    merge_idea_queries,
)
from glia.realtime.transcript import FastIntentProjector, TranscriptAccumulator

logger = structlog.get_logger(__name__)


def _is_socket_shutdown(error: BaseException) -> bool:
    """Recognise disconnects wrapped by an asyncio TaskGroup ExceptionGroup."""
    if isinstance(error, BaseExceptionGroup):
        return bool(error.exceptions) and all(
            _is_socket_shutdown(item) for item in error.exceptions
        )
    return isinstance(error, (WebSocketDisconnect, RuntimeError))


class RealtimeSocketSession:
    def __init__(
        self,
        websocket: WebSocket,
        debounce_ms: int,
        max_message_bytes: int,
        distiller: IntentDistiller | None = None,
        idea_synthesizer: IdeaSynthesizer | None = None,
        gate_jaccard_threshold: float = 0.4,
        discovery: DiscoveryService | None = None,
        discovery_debounce_ms: int = 600,
    ) -> None:
        self._websocket = websocket
        self._debounce_seconds = debounce_ms / 1_000
        self._debounce_ms = debounce_ms
        self._max_message_bytes = max_message_bytes
        self._transcript = TranscriptAccumulator()
        self._projector = FastIntentProjector()
        self._distiller = distiller or FixtureIntentDistiller(self._projector)
        self._idea_synthesizer = idea_synthesizer or LocalIdeaSynthesizer()
        self._local_idea_synthesizer = LocalIdeaSynthesizer()
        self._gate = DiscoveryGate(gate_jaccard_threshold)
        self._revision = 0
        self._pending_projection: asyncio.Task[None] | None = None
        self._discovery = discovery
        self._discovery_debounce_seconds = discovery_debounce_ms / 1_000
        self._pending_preview_discovery: asyncio.Task[None] | None = None
        self._preview_signature = ""
        self._pending_discovery: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._candidate_ids_by_revision: dict[int, set[str]] = {}
        self._session_id = str(uuid4())

    async def run(self) -> None:
        await self._websocket.accept()
        await self._send(SessionReady(session_id=self._session_id, debounce_ms=self._debounce_ms))
        try:
            while True:
                raw = await self._websocket.receive_text()
                if len(raw.encode("utf-8")) > self._max_message_bytes:
                    await self._send(
                        SocketError(
                            code="message_too_large",
                            detail="The WebSocket message exceeded the configured limit.",
                            recoverable=True,
                        )
                    )
                    continue
                await self._handle(raw)
        except WebSocketDisconnect:
            pass
        finally:
            await self._cancel_pending_projection()
            await self._cancel_pending_preview_discovery()
            await self._cancel_pending_discovery()

    async def _handle(self, raw: str) -> None:
        try:
            message = client_message_adapter.validate_json(raw)
        except ValidationError:
            await self._send(
                SocketError(
                    code="invalid_message",
                    detail="Message does not match the Glia realtime contract.",
                    recoverable=True,
                )
            )
            return
        except json.JSONDecodeError:
            await self._send(
                SocketError(
                    code="invalid_json",
                    detail="Message is not valid JSON.",
                    recoverable=True,
                )
            )
            return

        if isinstance(message, Ping):
            await self._send(Pong(event_id=message.event_id))
        elif isinstance(message, TranscriptDelta):
            if self._transcript.append_delta(message.event_id, message.item_id, message.delta):
                await self._send_transcript(message.item_id, complete=False)
                self._schedule_projection(
                    stable=False,
                    distill_text=self._transcript.item_text(message.item_id),
                )
        elif isinstance(message, TranscriptCompleted):
            if self._transcript.complete(message.event_id, message.item_id, message.transcript):
                await self._send_transcript(message.item_id, complete=True)
                # Distil the turn that just ended, not the whole accumulated session. Otherwise
                # a strong earlier subject ("green apples") can keep winning after the speaker
                # has plainly moved on ("cats and dogs"). The full snapshot is still sent to the
                # client as transcript history.
                await self._project(stable=True, distill_text=message.transcript)

    async def _send_transcript(self, item_id: str, complete: bool) -> None:
        await self._send(
            TranscriptAccepted(
                item_id=item_id,
                transcript=self._transcript.item_text(item_id),
                complete=complete,
            )
        )

    def _schedule_projection(self, stable: bool, distill_text: str | None = None) -> None:
        if self._pending_projection is not None:
            self._pending_projection.cancel()

        async def delayed_project() -> None:
            await asyncio.sleep(self._debounce_seconds)
            await self._project(stable=stable, distill_text=distill_text)

        self._pending_projection = asyncio.create_task(delayed_project())

    async def _project(self, stable: bool, distill_text: str | None = None) -> None:
        if stable:
            await self._cancel_pending_projection()
        transcript = self._transcript.snapshot()
        if not transcript:
            return
        projection_text = (
            distill_text.strip() if distill_text and distill_text.strip() else transcript
        )
        if stable:
            try:
                distilled = await self._distiller.distill(projection_text)
            except DistillationUnavailable as error:
                logger.warning(
                    "distiller.fallback",
                    error_type=type(error).__name__,
                    cause_type=type(error.__cause__).__name__ if error.__cause__ else None,
                )
                distilled = DistillationResult(
                    intent=self._projector.project(projection_text),
                    source="local",
                )
            if distilled.source == "pioneer":
                distilled = DistillationResult(
                    intent=self._fill_empty_pioneer_fields(
                        distilled.intent,
                        self._projector.project(projection_text),
                    ),
                    source="pioneer",
                )
            gate = self._gate.evaluate(distilled.intent)
        else:
            distilled = DistillationResult(
                intent=self._projector.project(projection_text),
                source="local",
            )
            gate = None

        self._revision += 1
        await self._send(
            IntentUpdated(
                revision=self._revision,
                transcript=transcript,
                intent=distilled.intent,
                stable=stable,
                source=distilled.source,
                should_discover=gate.should_discover if gate else False,
                change_reasons=gate.reasons if gate else [],
            )
        )
        if stable and gate is not None and gate.should_discover:
            # Fastino intentionally sees only the active turn, but OpenAI needs the complete
            # conversation to understand the company, product and design decisions accumulated
            # so far. The current intent remains the explicit visual focus for discovery.
            self._schedule_discovery(transcript, distilled.intent)
        elif not stable:
            self._schedule_preview_discovery(distilled.intent)

    @staticmethod
    def _fill_empty_pioneer_fields(
        pioneer: VisualIntent,
        local: VisualIntent,
    ) -> VisualIntent:
        """Complete partial Pioneer output without replacing its detected attributes."""
        return VisualIntent(
            subject=pioneer.subject.strip() or local.subject,
            moods=pioneer.moods or local.moods,
            styles=pioneer.styles or local.styles,
            palette=pioneer.palette or local.palette,
            composition=pioneer.composition.strip() or local.composition,
            medium=pioneer.medium.strip() or local.medium,
            era=pioneer.era.strip() or local.era,
        )

    def _schedule_preview_discovery(self, intent: VisualIntent) -> None:
        """Search only the free open lanes from debounced interim speech.

        This is the perception-speed path: it may place real photographs before the speaker has
        finished the sentence, but it can never reach Cala or spend a credit. The settled path
        later replaces it with the refined Fastino/OpenAI/Cala result.
        """
        queries = build_preview_queries(intent)
        signature = "\x1f".join(queries)
        if self._discovery is None or not queries or signature == self._preview_signature:
            return
        self._preview_signature = signature
        previous = self._pending_preview_discovery
        if previous is not None:
            previous.cancel()

        service = self._discovery
        revision = self._revision

        async def preview_discovery() -> None:
            try:
                await service.discover(
                    queries=queries,
                    revision=revision,
                    emit=self._send,
                    include_cited=False,
                )
            except (WebSocketDisconnect, RuntimeError):
                return
            except BaseExceptionGroup as error:
                if _is_socket_shutdown(error):
                    return
                raise

        self._pending_preview_discovery = asyncio.create_task(preview_discovery())

    def _schedule_discovery(self, transcript: str, intent: VisualIntent) -> None:
        """Search Fastino's direction now, then refine it with OpenAI in parallel."""
        base_queries = build_queries(intent)
        if not base_queries:
            return
        # Interim open-lane discovery is intentionally allowlisted. Arbitrary Fastino phrases
        # such as "enchufes minimalistas" used to broaden to "minimalistas" and fill the board
        # with fonts and insects before OpenAI could supply a semantic query.
        fast_queries = build_preview_queries(intent)
        previous = self._pending_discovery
        if previous is not None:
            previous.cancel()

        service = self._discovery
        revision = self._revision
        synthesizer = self._idea_synthesizer
        local_synthesizer = self._local_idea_synthesizer

        async def delayed_discovery() -> None:
            # A tiny coalescing window absorbs duplicate provider finals without making the
            # completion perceptibly later. The free open-preview lane is already filling the UI.
            await asyncio.sleep(min(self._discovery_debounce_seconds, 0.1))
            try:
                async def refine_and_discover() -> None:
                    try:
                        ideas = await synthesizer.synthesize(transcript, intent)
                    except IdeasUnavailable as error:
                        logger.warning(
                            "ideas.fallback",
                            error_type=type(error).__name__,
                            cause_type=type(error.__cause__).__name__ if error.__cause__ else None,
                        )
                        ideas = await local_synthesizer.synthesize(transcript, intent)
                    await self._send(
                        IdeasUpdated(
                            revision=revision,
                            ideas=ideas.ideas,
                            keywords=ideas.keywords,
                            source=ideas.source,
                        )
                    )
                    queries = merge_idea_queries(intent, ideas)
                    if service is not None and queries:
                        await service.discover(
                            queries=queries,
                            revision=revision,
                            emit=self._send,
                        )

                async with asyncio.TaskGroup() as group:
                    group.create_task(refine_and_discover())
                    if service is not None and fast_queries:
                        # Fastino has already identified the current visual subject. Let the free
                        # lanes search it immediately while OpenAI prepares more semantic English
                        # queries. Cala remains exclusively on the refined, settled call below.
                        group.create_task(
                            service.discover(
                                queries=fast_queries,
                                revision=revision,
                                emit=self._send,
                                include_cited=False,
                            )
                        )
            except (WebSocketDisconnect, RuntimeError):
                # The socket closed while a wave was in flight. Nothing to do.
                return
            except BaseExceptionGroup as error:
                if _is_socket_shutdown(error):
                    return
                raise

        self._pending_discovery = asyncio.create_task(delayed_discovery())

    async def _cancel_pending_discovery(self) -> None:
        task = self._pending_discovery
        self._pending_discovery = None
        if task is None or task is asyncio.current_task():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _cancel_pending_preview_discovery(self) -> None:
        task = self._pending_preview_discovery
        self._pending_preview_discovery = None
        if task is None or task is asyncio.current_task():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _cancel_pending_projection(self) -> None:
        task = self._pending_projection
        self._pending_projection = None
        if task is None or task is asyncio.current_task():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _send(self, message: ServerMessage) -> None:
        async with self._send_lock:
            if isinstance(message, CandidatesBatch):
                seen = self._candidate_ids_by_revision.setdefault(message.revision, set())
                candidates = [
                    candidate for candidate in message.candidates if candidate.id not in seen
                ]
                if not candidates:
                    return
                seen.update(candidate.id for candidate in candidates)
                message = message.model_copy(update={"candidates": candidates})
                for revision in tuple(self._candidate_ids_by_revision):
                    if revision < message.revision - 1:
                        self._candidate_ids_by_revision.pop(revision, None)
            await self._websocket.send_text(message.model_dump_json())
