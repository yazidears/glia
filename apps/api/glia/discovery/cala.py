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

import re
from typing import Any, Final

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
    CalaSearchResult,
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
