import asyncio
import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Protocol, cast

from openai import (
    APIError,
    AsyncOpenAI,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from glia.config import Settings
from glia.contracts import IdeaSource, VisualIntent
from glia.discovery.query import build_preview_queries, build_queries


class IdeasUnavailable(RuntimeError):
    pass


class _IdeaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ideas: list[str] = Field(min_length=1, max_length=3)
    keywords: list[str] = Field(min_length=1, max_length=8)
    search_queries: list[str] = Field(min_length=1, max_length=4)


@dataclass(frozen=True)
class IdeaResult:
    ideas: list[str]
    keywords: list[str]
    source: IdeaSource
    search_queries: list[str] = field(default_factory=list)


class IdeaSynthesizer(Protocol):
    async def synthesize(self, transcript: str, intent: VisualIntent) -> IdeaResult: ...


class LocalIdeaSynthesizer:
    async def synthesize(self, transcript: str, intent: VisualIntent) -> IdeaResult:
        del transcript
        queries = list(build_queries(intent))
        keywords = _intent_terms(intent)
        ideas = queries[:3] or keywords[:3] or [intent.subject]
        return IdeaResult(
            ideas=ideas,
            keywords=keywords or ideas,
            source="local",
            search_queries=queries,
        )


class OpenAIIdeaSynthesizer:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        cache_size: int,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._cache_size = cache_size
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )
        self._cache: OrderedDict[str, IdeaResult] = OrderedDict()

    async def synthesize(self, transcript: str, intent: VisualIntent) -> IdeaResult:
        cache_input = f"{transcript}\x1f{intent.model_dump_json()}"
        cache_key = hashlib.sha256(cache_input.encode("utf-8")).hexdigest()
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache.move_to_end(cache_key)
            return cached

        request: dict[str, object] = {
            "model": self._model,
            "instructions": (
                "The transcript is an ongoing conversation about a company, project, UI, mockup "
                "or other idea. Use the whole transcript as project context and visual_direction "
                "as the speaker's current focus. Return exactly three short visual ideas and up to "
                "eight important keyword phrases in the speaker's language for the UI. Also return "
                "one to four concise English search_queries optimised for Wikimedia Commons and "
                "Openverse. Search queries must name concrete, visually findable subjects and may "
                "translate the object plus its design intent into established visual concepts; do "
                "not concatenate the speaker's words literally when that would be a poor image "
                "search. For example, 'enchufes minimalistas' can become 'minimalist electrical "
                "outlet product design' or 'wall socket industrial design'. Preserve meaning, do "
                "not invent named entities, and do not revive an older subject unless it clearly "
                "remains part of the current project. Return no prose outside the schema."
            ),
            "input": json.dumps(
                {
                    "transcript": transcript,
                    "visual_direction": intent.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
            "text_format": _IdeaPayload,
            "max_output_tokens": 160,
            "store": False,
        }
        if self._model.startswith("gpt-5"):
            request["reasoning"] = {"effort": "none"}

        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.responses.parse(**request)  # type: ignore[arg-type]
        except (
            APIError,
            ContentFilterFinishReasonError,
            LengthFinishReasonError,
            TimeoutError,
            ValidationError,
        ) as error:
            raise IdeasUnavailable("OpenAI idea synthesis is temporarily unavailable") from error

        payload = cast(_IdeaPayload | None, response.output_parsed)
        if payload is None:
            raise IdeasUnavailable("OpenAI returned no structured visual ideas")

        result = IdeaResult(
            ideas=_clean(payload.ideas, limit=3),
            keywords=_clean(payload.keywords, limit=8),
            source="openai",
            search_queries=_clean(payload.search_queries, limit=4, max_length=80),
        )
        if not result.ideas or not result.keywords or not result.search_queries:
            raise IdeasUnavailable("OpenAI returned an empty visual idea set")
        self._cache[cache_key] = result
        self._cache.move_to_end(cache_key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return result


def build_idea_synthesizer(settings: Settings) -> IdeaSynthesizer:
    if settings.demo_mode != "live" or settings.openai_api_key is None:
        return LocalIdeaSynthesizer()
    return OpenAIIdeaSynthesizer(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_synthesis_model,
        timeout_seconds=settings.openai_synthesis_timeout_seconds,
        cache_size=settings.openai_synthesis_cache_size,
    )


def merge_idea_queries(intent: VisualIntent, result: IdeaResult) -> tuple[str, ...]:
    # The semantic planner translates conversational design intent into concrete English corpus
    # terms. The deterministic ladder remains the fast fallback when no planned query is present.
    # Keep the model's sharp visual direction, but reserve two rungs for measured concrete
    # corpus terms. Very specific design phrases often return one useful asset and many papers;
    # the concrete rungs fill the board with the actual object instead of broadening to an
    # ambiguous adjective such as "minimalistas".
    candidates = [
        *result.search_queries[:2],
        *build_preview_queries(intent),
        *build_queries(intent),
    ]
    return tuple(_clean(candidates, limit=4, max_length=80))


def _intent_terms(intent: VisualIntent) -> list[str]:
    return _clean(
        [
            intent.subject,
            *intent.moods,
            *intent.styles,
            *intent.palette,
            intent.composition,
            intent.medium,
            intent.era,
        ],
        limit=8,
    )


def _clean(values: list[str], *, limit: int, max_length: int = 96) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(value.split())[:max_length].strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned
