import asyncio
import json
from contextlib import suppress
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from glia.contracts import (
    IntentUpdated,
    Ping,
    Pong,
    ServerMessage,
    SessionReady,
    SocketError,
    TranscriptAccepted,
    TranscriptCompleted,
    TranscriptDelta,
    client_message_adapter,
)
from glia.realtime.transcript import FastIntentProjector, TranscriptAccumulator


class RealtimeSocketSession:
    def __init__(self, websocket: WebSocket, debounce_ms: int, max_message_bytes: int) -> None:
        self._websocket = websocket
        self._debounce_seconds = debounce_ms / 1_000
        self._debounce_ms = debounce_ms
        self._max_message_bytes = max_message_bytes
        self._transcript = TranscriptAccumulator()
        self._projector = FastIntentProjector()
        self._revision = 0
        self._pending_projection: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
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
                self._schedule_projection(stable=False)
        elif isinstance(message, TranscriptCompleted):
            if self._transcript.complete(message.event_id, message.item_id, message.transcript):
                await self._send_transcript(message.item_id, complete=True)
                await self._project(stable=True)

    async def _send_transcript(self, item_id: str, complete: bool) -> None:
        await self._send(
            TranscriptAccepted(
                item_id=item_id,
                transcript=self._transcript.item_text(item_id),
                complete=complete,
            )
        )

    def _schedule_projection(self, stable: bool) -> None:
        if self._pending_projection is not None:
            self._pending_projection.cancel()

        async def delayed_project() -> None:
            await asyncio.sleep(self._debounce_seconds)
            await self._project(stable=stable)

        self._pending_projection = asyncio.create_task(delayed_project())

    async def _project(self, stable: bool) -> None:
        if stable:
            await self._cancel_pending_projection()
        transcript = self._transcript.snapshot()
        if not transcript:
            return
        self._revision += 1
        await self._send(
            IntentUpdated(
                revision=self._revision,
                transcript=transcript,
                intent=self._projector.project(transcript),
                stable=stable,
            )
        )

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
            await self._websocket.send_text(message.model_dump_json())
