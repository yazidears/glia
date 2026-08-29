from functools import lru_cache
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, WebSocket
from fastapi.responses import JSONResponse

from glia.config import Settings, get_settings
from glia.contracts import HealthResponse, RealtimeTokenRequest, RealtimeTokenResponse
from glia.realtime.distiller import build_intent_distiller
from glia.realtime.socket import RealtimeSocketSession
from glia.realtime.token import (
    OpenAIRealtimeTokenBroker,
    RealtimeTokenBroker,
    TokenBrokerUnavailable,
    TokenMintFailed,
)

router = APIRouter()


@lru_cache(maxsize=1)
def get_token_broker() -> RealtimeTokenBroker:
    return OpenAIRealtimeTokenBroker(get_settings())


@router.get("/health")
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="glia-api",
        mode=settings.demo_mode,
        realtime="configured" if settings.openai_api_key else "unconfigured",
        distiller=(
            "fixture"
            if settings.demo_mode == "fixture"
            else "configured"
            if settings.pioneer_api_key
            else "unconfigured"
        ),
        # The candidate pipeline does not exist yet, so no configuration can make this true.
        # It becomes a real capability check when discovery lands; until then the client has to
        # be told plainly that no image can arrive, rather than being allowed to ask for one.
        image_discovery=False,
    )


@router.post("/api/realtime-token", response_model=RealtimeTokenResponse)
async def realtime_token(
    payload: RealtimeTokenRequest,
    request: Request,
    broker: Annotated[RealtimeTokenBroker, Depends(get_token_broker)],
) -> RealtimeTokenResponse | JSONResponse:
    correlation_id = request.headers.get("X-Request-ID", str(uuid4()))
    try:
        return await broker.mint(payload.client_id, payload.languages)
    except TokenBrokerUnavailable:
        return _problem(
            status=503,
            code="realtime_not_configured",
            title="Realtime transcription is not configured",
            detail="The server is missing its OpenAI API key.",
            correlation_id=correlation_id,
        )
    except TokenMintFailed:
        return _problem(
            status=502,
            code="realtime_upstream_failed",
            title="Realtime transcription is temporarily unavailable",
            detail="The server could not mint a short-lived transcription credential.",
            correlation_id=correlation_id,
        )


@router.websocket("/ws")
async def realtime_socket(websocket: WebSocket) -> None:
    settings = get_settings()
    session = RealtimeSocketSession(
        websocket,
        debounce_ms=settings.realtime_debounce_ms,
        max_message_bytes=settings.realtime_max_message_bytes,
        distiller=build_intent_distiller(settings),
        gate_jaccard_threshold=settings.distill_gate_jaccard_threshold,
    )
    await session.run()


def _problem(
    *, status: int, code: str, title: str, detail: str, correlation_id: str
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": f"https://glia.local/problems/{code}",
            "title": title,
            "status": status,
            "detail": detail,
            "code": code,
            "correlation_id": correlation_id,
        },
    )
