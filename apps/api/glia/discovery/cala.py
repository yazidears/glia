"""The one Cala call site.

Everything about this module is shaped by two facts from docs/PARTNERS.md § 2:

1. Auth is ``X-API-KEY``, **not** ``Authorization: Bearer``. A 401 is almost always this.
2. Cala returns no images. It resolves what the user means and cites the documents that
   answered; the image pipeline consumes ``context[].origins[].document.url`` later.

Two calls, in order: ``GET /entities`` to resolve the spoken subject, then
``POST /knowledge/search`` for the cited answer. ``/knowledge/query`` is deliberately not used
— it returns no ``explainability`` and no ``context``, so no citations and no URLs.

Every request passes the debounce, the cache and the ledger in `budget.py` before it is made.
There is no second path to Cala, and adding one is how the budget disappears.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import urljoin

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from glia.config import Settings
from glia.contracts import (
    CalaEntityHit,
    CalaOrigin,
    CalaSearchEntity,
    CalaSearchResult,
    Candidate,
    DiscoverResponse,
    EvidenceItem,
    LedgerSnapshot,
)
from glia.discovery.budget import (
    CreditLedger,
    SessionDebounce,
    TtlCache,
    cache_key,
)
from glia.discovery.fetch import (
    DocumentFetcher,
    FetchFailed,
    FetchRejected,
    TextDocument,
    validate_remote_url,
)

logger = structlog.get_logger(__name__)

# Straight and curly apostrophes both: transcription providers emit either.
_WORD = re.compile("[A-Za-z][A-Za-z'\u2019-]*")

#: Openers and fillers that a spoken sentence starts with, which would otherwise be mistaken
#: for a capitalised proper noun at position zero.
_SUBJECT_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "about",
        "actually",
        "all",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "get",
        "had",
        "has",
        "have",
        "her",
        "here",
        "his",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "just",
        "kind",
        "know",
        "like",
        "look",
        "looking",
        "maybe",
        "me",
        "mean",
        "more",
        "my",
        "no",
        "not",
        "of",
        "off",
        "ok",
        "okay",
        "on",
        "one",
        "or",
        "our",
        "out",
        "really",
        "right",
        "say",
        "see",
        "she",
        "should",
        "show",
        "so",
        "some",
        "something",
        "sort",
        "story",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "thing",
        "think",
        "this",
        "those",
        "to",
        "up",
        "us",
        "very",
        "want",
        "was",
        "we",
        "well",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "yeah",
        "you",
        "your",
    }
)

_MAX_SUBJECT_WORDS: Final = 6

# Entity types that can act as a concrete visual reference. Financial metrics, laws and other
# valid Cala entities stay in the evidence response, but they do not belong in the quiet
# inspiration rail beneath the canvas.
_VISUAL_ENTITY_TYPES: Final[frozenset[str]] = frozenset(
    {
        "company",
        "facility",
        "gpe",
        "location",
        "organization",
        "person",
        "product",
        "workofart",
    }
)


class CalaNotConfigured(Exception):
    """No API key. The route answers honestly rather than pretending to have searched."""


class CalaRateLimited(Exception):
    """Upstream 429. Surfaced as a typed status, never as a 500."""


class CalaUpstreamError(Exception):
    """Anything else upstream. The vendor body never leaves this module."""


class CalaRetryableError(CalaUpstreamError):
    """A failure that provably never reached Cala, and is therefore free to repeat.

    Nothing else is retryable here, because a retry on a billable endpoint is a second credit.
    A read timeout in particular is NOT this: the query has already been accepted and is
    running upstream, so retrying it buys the same answer twice. Measured against the live API
    on 29 Aug 2026 — a cold `knowledge/search` took 45.7s, which a naive read-timeout retry
    turns into three charged queries for one question.
    """


class _LeadImageParser(HTMLParser):
    """Collect declared page images without treating remote markup as trusted HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.open_graph: list[str] = []
        self.twitter: list[str] = []
        self.image_src: list[str] = []
        self.inline: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value for name, value in attrs if value is not None}
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content")
            if content and key in {"og:image", "og:image:secure_url"}:
                self.open_graph.append(content)
            elif content and key in {"twitter:image", "twitter:image:src"}:
                self.twitter.append(content)
        elif tag.lower() == "link" and "image_src" in (values.get("rel") or "").lower():
            if href := values.get("href"):
                self.image_src.append(href)
        elif tag.lower() == "img":
            if src := values.get("src"):
                self.inline.append(src)

    @property
    def candidates(self) -> list[str]:
        return [*self.open_graph, *self.twitter, *self.image_src, *self.inline]


def extract_lead_image(document: TextDocument) -> str | None:
    """Return the first public https image declared by a Cala-cited page."""
    parser = _LeadImageParser()
    try:
        parser.feed(document.body)
    except Exception as error:
        raise FetchFailed("Cited document markup could not be parsed") from error
    for raw in parser.candidates:
        try:
            return validate_remote_url(urljoin(document.final_url, raw))
        except FetchRejected:
            continue
    return None


def extract_subject(transcript: str) -> str | None:
    """A naive noun-phrase heuristic. There is no distiller yet, and this is explicitly the
    placeholder for one: the longest run of capitalised words that is not a sentence opener,
    falling back to the trailing content words.

    Deliberately not clever. Getting this wrong costs a wasted entity lookup, and the cost of
    a wrong guess is bounded by the debounce and the ledger rather than by the heuristic.
    """
    words = _WORD.findall(transcript)
    if not words:
        return None

    best: list[str] = []
    run: list[str] = []
    for index, word in enumerate(words):
        capitalised = word[:1].isupper()
        # A capitalised word in first position is just the start of a sentence.
        opener = index == 0 or words[index - 1].endswith(".")
        if capitalised and not (opener and word.casefold() in _SUBJECT_STOPWORDS):
            run.append(word)
            if len(run) > len(best):
                best = list(run)
        else:
            run = []

    if best:
        return " ".join(best[:_MAX_SUBJECT_WORDS])

    content = [word for word in words if word.casefold() not in _SUBJECT_STOPWORDS]
    if not content:
        return None
    return " ".join(content[-_MAX_SUBJECT_WORDS:])


def _entity_rows(payload: Any) -> list[Any]:
    """`GET /entities` is documented by its row shape (`{id, name, entity_type, description}`)
    but not by its envelope, so accept a bare list or the two obvious wrappers and nothing
    else. Anything unrecognised resolves to no entity rather than to a guess."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for field_name in ("entities", "results", "data"):
            rows = payload.get(field_name)
            if isinstance(rows, list):
                return rows
    return []


def _first_entity(rows: list[Any]) -> CalaEntityHit | None:
    if not rows or not isinstance(rows[0], dict):
        return None
    return CalaEntityHit.model_validate(rows[0])


def join_evidence(result: CalaSearchResult) -> list[EvidenceItem]:
    """Join ``explainability[].references`` onto ``context[].id``.

    This is the salience signal: it says which quoted evidence actually carried the answer, as
    opposed to merely being retrieved. Cited items sort first so the UI can lead with them
    without inventing a score.
    """
    cited: set[str] = {
        reference for explanation in result.explainability for reference in explanation.references
    }
    items = [
        EvidenceItem(
            id=item.id,
            content=item.content,
            origins=item.origins,
            carried_answer=item.id in cited,
        )
        for item in result.context
    ]
    return sorted(items, key=lambda item: not item.carried_answer)


def visual_entity_query(direction: str) -> str:
    """Ask Cala for sourced real-world anchors, not anonymous image-search keywords.

    The same ``knowledge/search`` response still feeds Lane A through its citations. Its
    ``entities`` additionally feed the small related-reference rail, so this does not add a
    second Cala call or spend a second credit.
    """
    cleaned = " ".join(direction.split())[:80]
    return (
        "Which companies, products, works of art, facilities, places or people are strongly "
        f"associated with this visual direction: {cleaned}? Explain the visual connection and "
        "support the suggestions with authoritative sources."
    )


def visual_entity_for(
    evidence: EvidenceItem,
    origin: CalaOrigin,
    entities: list[CalaSearchEntity],
) -> CalaSearchEntity | None:
    """Match a cited page to a useful entity without inventing a visual relationship."""
    eligible = [
        entity
        for entity in entities
        if entity.entity_type is not None
        and entity.entity_type.replace("_", "").casefold() in _VISUAL_ENTITY_TYPES
    ]
    if not eligible:
        return None

    document_name = origin.document.name if origin.document is not None else None
    haystack = " ".join(part for part in (evidence.content, document_name) if part).casefold()
    for entity in eligible:
        aliases = [entity.name, *entity.mentions]
        if any(alias.strip() and alias.casefold() in haystack for alias in aliases):
            return entity

    # A single returned visual entity is unambiguous even when the evidence quote uses a
    # pronoun. Multiple unmatched entities remain absent rather than being paired by position.
    return eligible[0] if len(eligible) == 1 else None


class CalaClient:
    """Owns the credentials, the timeouts, the retry policy and the budget controls."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.cala_base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            connect=settings.cala_connect_timeout_seconds,
            read=settings.cala_request_timeout_seconds,
            write=settings.cala_connect_timeout_seconds,
            pool=settings.cala_connect_timeout_seconds,
        )
        self.ledger = CreditLedger(budget=settings.cala_credit_budget)
        self.debounce = SessionDebounce(settings.cala_min_seconds_between_queries)
        #: Keyed on a hash of the normalised search input, holding the raw upstream JSON.
        self.cache: TtlCache[dict[str, Any]] = TtlCache(settings.cala_cache_ttl_seconds)
        #: Entity resolution is cached on the same terms as search. It has to be: a demo script
        #: re-run must cost zero, and an uncached entity lookup bills on every repeat even when
        #: the search behind it is a hit. Whether it bills at all is undocumented — which is
        #: exactly why it is not left to chance.
        self.entity_cache: TtlCache[list[Any]] = TtlCache(settings.cala_cache_ttl_seconds)
        self._replies: dict[str, DiscoverResponse] = {}

    @property
    def configured(self) -> bool:
        return self._settings.cala_api_key is not None

    def snapshot(self) -> LedgerSnapshot:
        return LedgerSnapshot(
            budget=self.ledger.budget,
            spent=self.ledger.spent,
            remaining=self.ledger.remaining,
            search_calls=self.ledger.search_calls,
            entity_calls=self.ledger.entity_calls,
        )

    def last_reply(self, session_id: str) -> DiscoverResponse | None:
        return self._replies.get(session_id)

    def remember_reply(self, session_id: str, response: DiscoverResponse) -> None:
        self._replies[session_id] = response

    async def resolve_entity(self, subject: str) -> tuple[CalaEntityHit | None, bool]:
        """`GET /entities?name=…&limit=…` — turn a messy spoken mention into a typed entity.

        Returns the first hit and whether it came from cache.
        """
        key = cache_key(subject)
        cached_rows = self.entity_cache.get(key)
        if cached_rows is not None:
            logger.info("cala.entities.cache_hit", key=key[:12])
            return _first_entity(cached_rows), True

        payload = await self._request(
            "GET",
            "/entities",
            kind="entities",
            params={"name": subject, "limit": self._settings.cala_entity_limit},
        )
        rows = _entity_rows(payload)
        self.entity_cache.set(key, rows)
        return _first_entity(rows), False

    async def search(self, query: str) -> tuple[CalaSearchResult, bool]:
        """`POST /knowledge/search`. Returns the parsed result and whether it was cached.

        The cache is checked before the ledger, so a repeated demo script costs nothing.
        """
        key = cache_key(query)
        hit = self.cache.get(key)
        if hit is not None:
            logger.info("cala.search.cache_hit", key=key[:12])
            return CalaSearchResult.model_validate(hit), True

        payload = await self._request(
            "POST",
            "/knowledge/search",
            kind="search",
            json={"input": query, "explainability": True, "return_entities": True},
        )
        if not isinstance(payload, dict):
            raise CalaUpstreamError("Cala returned a non-object search response.")
        # Retain the raw JSON: the source panel must render identically from cache.
        self.cache.set(key, payload)
        return CalaSearchResult.model_validate(payload), False

    async def _request(
        self,
        method: str,
        path: str,
        *,
        kind: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        key = self._settings.cala_api_key
        if key is None:
            raise CalaNotConfigured("CALA_API_KEY is not set.")

        # Charged before the call: Cala bills the query, not our ability to read the answer.
        self.ledger.reserve(kind)
        logger.info(
            "cala.request",
            endpoint=path,
            kind=kind,
            credits_spent=self.ledger.spent,
            credits_remaining=self.ledger.remaining,
            search_calls=self.ledger.search_calls,
            entity_calls=self.ledger.entity_calls,
        )

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.4, max=3),
                retry=retry_if_exception_type(CalaRetryableError),
                reraise=True,
            ):
                with attempt:
                    return await self._send(
                        method, path, key=key.get_secret_value(), params=params, json=json
                    )
        except RetryError as error:  # pragma: no cover - reraise=True makes this unreachable
            raise CalaUpstreamError("Cala did not respond.") from error
        raise CalaUpstreamError("Cala did not respond.")

    async def _send(
        self,
        method: str,
        path: str,
        *,
        key: str,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
    ) -> Any:
        headers = {
            # X-API-KEY, not Authorization: Bearer. See docs/PARTNERS.md § 2.
            "X-API-KEY": key,
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                response = await client.request(
                    method, path, params=params, json=json, headers=headers
                )
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:
            # Never left the machine: safe to try again.
            raise CalaRetryableError("Cala is unreachable.") from error
        except httpx.HTTPError as error:
            # Sent but not answered — a read timeout, a dropped connection mid-response. The
            # query is running upstream and the credit is spent, so this surfaces instead of
            # being repeated.
            raise CalaUpstreamError("Cala did not answer in time.") from error

        # 429 and 422 are answers, not failures: retrying a rate limit spends the budget faster
        # and retrying a validation error just repeats it.
        if response.status_code == 429:
            raise CalaRateLimited("rate_limit_exceeded")
        if response.status_code == 422:
            raise CalaUpstreamError("Cala rejected the query as invalid.")
        if response.status_code >= 500:
            # Also not retried: an upstream 500 may still have run and billed the query.
            raise CalaUpstreamError(f"Cala returned {response.status_code}.")
        if response.status_code >= 400:
            # The upstream body is logged, never returned — it is a vendor response and may
            # carry detail we have no business putting in an HTTP reply.
            logger.warning("cala.request.rejected", status=response.status_code, endpoint=path)
            raise CalaUpstreamError(f"Cala returned {response.status_code}.")

        try:
            return response.json()
        except ValueError as error:
            raise CalaUpstreamError("Cala returned a body that is not JSON.") from error


class CalaCitedLane:
    """Turn Cala citations into Lane A candidates by reading the cited pages.

    Cala itself returns no image fields. This lane consumes only
    ``context[].origins[].document.url`` and asks the guarded document fetcher for each page's
    declared lead image. The browser displays that origin image directly with attribution.
    """

    name = "cala"

    def __init__(
        self,
        *,
        client: CalaClient,
        document_fetcher: DocumentFetcher,
        min_seconds_between_queries: float,
        max_documents: int = 6,
    ) -> None:
        self._client = client
        self._document_fetcher = document_fetcher
        self._min_seconds = min_seconds_between_queries
        self._max_documents = max_documents
        self._last_attempt_at = 0.0
        self._cache: dict[str, list[Candidate]] = {}

    async def search(self, query: str) -> list[Candidate]:
        cached = self._cache.get(query)
        if cached is not None:
            return cached

        now = time.monotonic()
        if now - self._last_attempt_at < self._min_seconds:
            logger.info("cala.lane.debounced")
            return []
        self._last_attempt_at = now

        result, _cached = await self._client.search(visual_entity_query(query))
        jobs: list[tuple[EvidenceItem, CalaOrigin, CalaSearchEntity | None]] = []
        for evidence in join_evidence(result):
            for origin in evidence.origins:
                document = origin.document
                if document is None or not document.url:
                    continue
                jobs.append(
                    (evidence, origin, visual_entity_for(evidence, origin, result.entities))
                )
                if len(jobs) >= self._max_documents:
                    break
            if len(jobs) >= self._max_documents:
                break

        candidates = await asyncio.gather(
            *(
                self._candidate(evidence, origin, entity, index)
                for index, (evidence, origin, entity) in enumerate(jobs)
            )
        )
        found = [candidate for candidate in candidates if candidate is not None]
        self._cache[query] = found
        return found

    async def _candidate(
        self,
        evidence: EvidenceItem,
        origin: CalaOrigin,
        entity: CalaSearchEntity | None,
        index: int,
    ) -> Candidate | None:
        document = origin.document
        if document is None or not document.url:
            return None
        try:
            page = await self._document_fetcher.fetch(document.url)
            image_url = extract_lead_image(page)
        except (FetchFailed, FetchRejected):
            return None
        if image_url is None:
            return None

        digest = hashlib.sha256(f"{page.final_url}\0{image_url}".encode()).hexdigest()[:20]
        publisher = origin.source.name if origin.source is not None else None
        return Candidate(
            id=f"cala:{digest}",
            lane="cited",
            image_url=image_url,
            source_url=page.final_url,
            publisher=publisher,
            title=document.name,
            evidence=evidence.content,
            entity_name=entity.name if entity is not None else None,
            entity_type=entity.entity_type if entity is not None else None,
            width=None,
            height=None,
            score=round(max(0.5, 1.0 - index * 0.06), 4),
        )
