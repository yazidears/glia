from functools import lru_cache
from typing import Annotated, Literal
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, Request, WebSocket
from fastapi.responses import JSONResponse

from glia.config import Settings, get_settings
from glia.contracts import (
    CalaEntityHit,
    DiscoverRequest,
    DiscoverResponse,
    LedgerSnapshot,
    RealtimeTokenRequest,
    RealtimeTokenResponse,
)
from glia.discovery.budget import BudgetExhausted
from glia.discovery.cala import (
    CalaClient,
    CalaNotConfigured,
    CalaRateLimited,
    CalaUpstreamError,
    extract_subject,
    join_evidence,
)
from glia.realtime.socket import RealtimeSocketSession
from glia.realtime.token import (
    OpenAIRealtimeTokenBroker,
    RealtimeTokenBroker,
    TokenBrokerUnavailable,
    TokenMintFailed,
)

router = APIRouter()


logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def get_token_broker() -> RealtimeTokenBroker:
    return OpenAIRealtimeTokenBroker(get_settings())


@lru_cache(maxsize=1)
def get_cala_client() -> CalaClient:
    """One client, one ledger, one cache, for the life of the process. The `lru_cache` is what
    makes "one Cala call site" true at runtime rather than only by convention."""
    return CalaClient(get_settings())


@router.get("/health")
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    return {
        "status": "ok",
        "service": "glia-api",
        "mode": settings.demo_mode,
        "realtime": "configured" if settings.openai_api_key else "unconfigured",
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


@router.get("/v1/ledger", response_model=LedgerSnapshot)
async def ledger(
    client: Annotated[CalaClient, Depends(get_cala_client)],
) -> LedgerSnapshot:
    """Credits spent this process. In-process, so it resets with the API — that is a known
    limitation of today's counter, not a claim about the monthly pool."""
    return client.snapshot()


@router.post("/v1/discover", response_model=DiscoverResponse)
async def discover(
    payload: DiscoverRequest,
    request: Request,
    client: Annotated[CalaClient, Depends(get_cala_client)],
) -> DiscoverResponse | JSONResponse:
    """Resolve the spoken subject against Cala, then find the sources that answer it.

    Three gates stand in front of the two upstream calls, and a settled turn that fails any of
    them costs nothing: the per-session debounce replays the last answer, the cache replays a
    previous one, and the ledger refuses outright once the budget is gone.
    """
    correlation_id = request.headers.get("X-Request-ID", str(uuid4()))
    subject = extract_subject(payload.transcript)

    if not client.configured:
        return _problem(
            status=503,
            code="cala_not_configured",
            title="Source discovery is not configured",
            detail="The server is missing its Cala API key.",
            correlation_id=correlation_id,
        )

    if subject is None:
        return _empty(payload, subject=None, query="", client=client, correlation_id=correlation_id)

    # Debounce before anything billable. A request inside the window replays this session's
    # last answer rather than buying a new one.
    waiting = client.debounce.seconds_remaining(payload.session_id)
    if waiting > 0:
        previous = client.last_reply(payload.session_id)
        logger.info(
            "cala.discover.debounced", session_id=payload.session_id, seconds_remaining=waiting
        )
        if previous is not None:
            return previous.model_copy(update={"cached": True, "correlation_id": correlation_id})
        return _empty(
            payload, subject=subject, query="", client=client, correlation_id=correlation_id
        )

    try:
        entity = await client.resolve_entity(subject)
        query = _query_for(subject, entity)
        result, cached = await client.search(query)
    except BudgetExhausted:
        logger.warning("cala.discover.budget_exhausted", budget=client.ledger.budget)
        return _terminal(
            payload, "budget_exhausted", subject, client=client, correlation_id=correlation_id
        )
    except CalaRateLimited:
        logger.warning("cala.discover.rate_limited", session_id=payload.session_id)
        return _terminal(
            payload, "rate_limited", subject, client=client, correlation_id=correlation_id
        )
    except CalaNotConfigured:
        return _problem(
            status=503,
            code="cala_not_configured",
            title="Source discovery is not configured",
            detail="The server is missing its Cala API key.",
            correlation_id=correlation_id,
        )
    except CalaUpstreamError:
        # Logged upstream with the endpoint; the vendor body never reaches the client.
        logger.warning("cala.discover.upstream_failed", correlation_id=correlation_id)
        return _problem(
            status=502,
            code="cala_upstream_failed",
            title="Source discovery is temporarily unavailable",
            detail="The upstream knowledge service did not return a usable answer.",
            correlation_id=correlation_id,
        )

    if not cached:
        client.debounce.mark(payload.session_id)

    context = join_evidence(result)
    # Cala's coverage is finance, legal and health; most spoken subjects miss it. An answer with
    # no cited context is normal operation, and saying so is more honest than rendering an
    # ungrounded answer as though it were sourced.
    status = "ok" if context else "empty"
    response = DiscoverResponse(
        status=status,
        session_id=payload.session_id,
        subject=subject,
        query=query,
        entity=entity,
        answer=result.content if context else None,
        explainability=result.explainability,
        context=context,
        entities=result.entities,
        cached=cached,
        ledger=client.snapshot(),
        correlation_id=correlation_id,
    )
    client.remember_reply(payload.session_id, response)
    return response


def _query_for(subject: str, entity: CalaEntityHit | None) -> str:
    """The resolved name beats the heard one — resolution is the point of the entity step."""
    return entity.name if entity is not None and entity.name else subject


def _empty(
    payload: DiscoverRequest,
    *,
    subject: str | None,
    query: str,
    client: CalaClient,
    correlation_id: str,
) -> DiscoverResponse:
    return DiscoverResponse(
        status="empty",
        session_id=payload.session_id,
        subject=subject,
        query=query,
        entity=None,
        answer=None,
        explainability=[],
        context=[],
        entities=[],
        cached=True,
        ledger=client.snapshot(),
        correlation_id=correlation_id,
    )


def _terminal(
    payload: DiscoverRequest,
    status: Literal["rate_limited", "budget_exhausted"],
    subject: str | None,
    *,
    client: CalaClient,
    correlation_id: str,
) -> DiscoverResponse:
    """Rate limiting and an exhausted budget are answers with a 200, not server errors. The UI
    tells the truth about them, which it cannot do from a 500."""
    return DiscoverResponse(
        status=status,
        session_id=payload.session_id,
        subject=subject,
        query="",
        entity=None,
        answer=None,
        explainability=[],
        context=[],
        entities=[],
        cached=False,
        ledger=client.snapshot(),
        correlation_id=correlation_id,
    )


@router.websocket("/ws")
async def realtime_socket(websocket: WebSocket) -> None:
    settings = get_settings()
    session = RealtimeSocketSession(
        websocket,
        debounce_ms=settings.realtime_debounce_ms,
        max_message_bytes=settings.realtime_max_message_bytes,
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
