from functools import lru_cache
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse

from glia.config import Settings, get_settings
from glia.contracts import RealtimeTokenRequest, RealtimeTokenResponse
from glia.discovery.fetch import FetchFailed, FetchRejected, ImageFetcher
from glia.discovery.service import DiscoveryService, build_discovery_service
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


@lru_cache(maxsize=1)
def get_discovery_service() -> DiscoveryService:
    """One process-wide service so its query cache is shared across sessions."""
    return build_discovery_service(get_settings())


@lru_cache(maxsize=1)
def get_image_fetcher() -> ImageFetcher:
    settings = get_settings()
    return ImageFetcher(
        allowlist=settings.image_host_allowlist,
        user_agent=settings.image_fetch_user_agent,
        max_bytes=settings.image_fetch_max_bytes,
        connect_timeout=settings.image_fetch_connect_timeout,
        total_timeout=settings.image_fetch_total_timeout,
    )


@router.get("/health")
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    return {
        "status": "ok",
        "service": "glia-api",
        "mode": settings.demo_mode,
        "realtime": "configured" if settings.openai_api_key else "unconfigured",
        "distiller": (
            "fixture"
            if settings.demo_mode == "fixture"
            else "configured"
            if settings.pioneer_api_key
            else "unconfigured"
        ),
    }


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


@router.get("/api/image", response_model=None)
async def image_proxy(
    request: Request,
    fetcher: Annotated[ImageFetcher, Depends(get_image_fetcher)],
    url: Annotated[str, Query(max_length=2_000)],
) -> StreamingResponse | JSONResponse:
    """Re-serve a discovered image so the browser never hot-links a third party.

    `url` is remote-supplied and is treated as such: ImageFetcher owns the
    scheme and host allowlists, the resolved-address check, redirect refusal,
    the content-type check and the streamed byte cap.
    """
    correlation_id = request.headers.get("X-Request-ID", str(uuid4()))
    try:
        stream = await fetcher.open(url)
    except FetchRejected:
        return _problem(
            status=400,
            code="image_url_rejected",
            title="That image URL is not fetchable",
            detail="The requested URL is not an allowed image source.",
            correlation_id=correlation_id,
        )
    except FetchFailed:
        return _problem(
            status=502,
            code="image_upstream_failed",
            title="The image host did not return an image",
            detail="The upstream image could not be retrieved.",
            correlation_id=correlation_id,
        )
    return StreamingResponse(
        stream.chunks,
        media_type=stream.content_type,
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
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
        discovery=get_discovery_service(),
        discovery_debounce_ms=settings.discovery_debounce_ms,
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
