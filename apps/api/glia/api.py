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
    GenerateRequest,
    GenerateResponse,
    HealthResponse,
    LedgerSnapshot,
    RealtimeTokenRequest,
    RealtimeTokenResponse,
    VisualIntent,
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
from glia.generation.fal import (
    FalClient,
    FalNotConfigured,
    FalReferenceUnavailable,
    FalTimedOut,
    FalUpstreamError,
    reference_urls,
)
from glia.generation.fixture import FIXTURE_IMAGE_URL, fixture_model
from glia.generation.synthesis import (
    PromptSynthesiser,
    SynthesisUnavailable,
    build_prompt_synthesiser,
)
from glia.realtime.distiller import (
    DistillationUnavailable,
    IntentDistiller,
    build_intent_distiller,
)
from glia.realtime.socket import RealtimeSocketSession
from glia.realtime.token import (
    OpenAIRealtimeTokenBroker,
    RealtimeTokenBroker,
    TokenBrokerUnavailable,
    TokenMintFailed,
)
from glia.realtime.transcript import FastIntentProjector

router = APIRouter()


logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def get_token_broker() -> RealtimeTokenBroker:
    return OpenAIRealtimeTokenBroker(get_settings())


@lru_cache(maxsize=1)
def get_fal_client() -> FalClient:
    """One client for the life of the process, because the one-in-flight set lives on it. A
    per-request client would make "exactly one generation per session" unenforceable."""
    return FalClient(get_settings())


@lru_cache(maxsize=1)
def get_prompt_synthesiser() -> PromptSynthesiser:
    return build_prompt_synthesiser(get_settings())


@lru_cache(maxsize=1)
def get_generate_distiller() -> IntentDistiller:
    """The same distiller the socket runs, reached over HTTP. Generate needs the current
    VisualIntent and the socket's copy lives on a connection this request does not have, so it
    is recomputed from the transcript the client sent rather than guessed at."""
    return build_intent_distiller(get_settings())


@lru_cache(maxsize=1)
def get_cala_client() -> CalaClient:
    """One client, one ledger, one cache, for the life of the process. The `lru_cache` is what
    makes "one Cala call site" true at runtime rather than only by convention."""
    return CalaClient(get_settings())


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
        entity, entity_cached = await client.resolve_entity(subject)
        query = _query_for(subject, entity)
        result, search_cached = await client.search(query)
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

    # Only a turn that actually bought something restarts the debounce window; a fully cached
    # turn cost nothing and should not delay the next real question.
    cached = entity_cached and search_cached
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


@router.post("/v1/generate", response_model=GenerateResponse)
async def generate(
    payload: GenerateRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    fal: Annotated[FalClient, Depends(get_fal_client)],
    synthesiser: Annotated[PromptSynthesiser, Depends(get_prompt_synthesiser)],
    distiller: Annotated[IntentDistiller, Depends(get_generate_distiller)],
) -> GenerateResponse | JSONResponse:
    """Transcript + intent + pins → one prompt → one image.

    Two properties are load-bearing and everything else here serves them.

    The pins are a real input. Every pin's title reaches the synthesis, and the pins fal can
    actually fetch — public https only — additionally go out as `image_urls`. When none can be
    fetched, `reference_count` is 0 and nothing in the reply claims otherwise.

    The prompt is a deliverable. It is returned verbatim on every outcome that reached fal,
    including the timeout, because it is the answer to "here is what we understood you to
    mean" and that answer survives a generation that did not land.
    """
    correlation_id = request.headers.get("X-Request-ID", str(uuid4()))
    live = settings.demo_mode == "live"

    if live and not fal.configured:
        return _problem(
            status=503,
            code="fal_not_configured",
            title="Generation is not configured",
            detail="The server is missing its fal API key.",
            correlation_id=correlation_id,
        )

    # fal allows two concurrent requests on a new account. One per session, and the second is
    # refused rather than queued — a queued click spends a generation the user cannot see.
    if not fal.acquire(payload.session_id):
        logger.info("generate.refused", session_id=payload.session_id, reason="already_generating")
        return GenerateResponse(
            status="already_generating",
            session_id=payload.session_id,
            image_url=None,
            prompt="",
            model="",
            reference_count=0,
            correlation_id=correlation_id,
        )

    try:
        intent = await _intent_for(distiller, payload.transcript)
        try:
            prompt = await synthesiser.synthesise(payload.transcript, intent, payload.pins)
        except SynthesisUnavailable:
            logger.warning("generate.synthesis.unavailable", correlation_id=correlation_id)
            return _problem(
                status=502,
                code="synthesis_failed",
                title="The prompt could not be written",
                detail="The server could not turn this session into a prompt it can show you.",
                correlation_id=correlation_id,
            )

        references = reference_urls(payload.pins, settings.fal_max_reference_images)
        model = fal.model_for(references)
        logger.info(
            "generate.prompt_ready",
            session_id=payload.session_id,
            model=model,
            pins=len(payload.pins),
            reference_count=len(references),
        )

        if not live:
            # No socket opened. The prompt is the real one; the image is visibly a stand-in.
            return GenerateResponse(
                status="ok",
                session_id=payload.session_id,
                image_url=FIXTURE_IMAGE_URL,
                prompt=prompt,
                model=fixture_model(model),
                reference_count=len(references),
                correlation_id=correlation_id,
            )

        try:
            image_url = await fal.generate(model=model, prompt=prompt, references=references)
        except FalTimedOut:
            # A 200 with a typed status, not a 504: the prompt is still worth showing, and the
            # generation may yet land upstream. Saying "timed out" is the honest version.
            logger.warning("generate.timed_out", session_id=payload.session_id, model=model)
            return GenerateResponse(
                status="timeout",
                session_id=payload.session_id,
                image_url=None,
                prompt=prompt,
                model=model,
                reference_count=len(references),
                correlation_id=correlation_id,
            )
        except FalReferenceUnavailable:
            # Not a transport failure: fal reached the URL and could not have it. Wikimedia's
            # `upload.wikimedia.org`, measured on 29 Aug 2026, answers a blank User-Agent with
            # 403 — which is what fal's fetcher sends — so this is a live case, not a theory.
            logger.warning(
                "generate.reference_unavailable",
                session_id=payload.session_id,
                reference_count=len(references),
            )
            return GenerateResponse(
                status="reference_unavailable",
                session_id=payload.session_id,
                image_url=None,
                prompt=prompt,
                model=model,
                reference_count=len(references),
                correlation_id=correlation_id,
            )
        except FalNotConfigured:
            return _problem(
                status=503,
                code="fal_not_configured",
                title="Generation is not configured",
                detail="The server is missing its fal API key.",
                correlation_id=correlation_id,
            )
        except FalUpstreamError:
            logger.warning("generate.upstream_failed", correlation_id=correlation_id)
            return _problem(
                status=502,
                code="fal_upstream_failed",
                title="Generation is temporarily unavailable",
                detail="The upstream image service did not return an image.",
                correlation_id=correlation_id,
            )

        return GenerateResponse(
            status="ok",
            session_id=payload.session_id,
            image_url=image_url,
            prompt=prompt,
            model=model,
            reference_count=len(references),
            correlation_id=correlation_id,
        )
    finally:
        fal.release(payload.session_id)


async def _intent_for(distiller: IntentDistiller, transcript: str) -> VisualIntent:
    """The distilled attributes, or the local projection when the distiller is unavailable.

    Generation is the last beat of the demo and must not fail on a Pioneer hiccup: a weaker
    intent produces a weaker prompt, which is a better outcome than no image at all.
    """
    try:
        return (await distiller.distill(transcript)).intent
    except DistillationUnavailable:
        logger.warning("generate.distill.unavailable")
        return FastIntentProjector().project(transcript)


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
