import asyncio
import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from glia.config import Settings
from glia.contracts import IntentChangeReason, IntentSource, VisualIntent
from glia.realtime.transcript import FastIntentProjector

VISUAL_DIRECTION_SCHEMA: dict[str, object] = {
    "structures": {
        "visual_direction": {
            "fields": [
                {
                    "name": "subject",
                    "dtype": "str",
                    "description": "The main visual subject named in the text",
                },
                {
                    "name": "mood",
                    "dtype": "list",
                    "description": "Explicit emotional or atmospheric qualities",
                },
                {
                    "name": "style",
                    "dtype": "list",
                    "description": "Explicit visual styles or aesthetic movements",
                },
                {
                    "name": "palette",
                    "dtype": "list",
                    "description": "Explicit colours or colour palette terms",
                },
                {
                    "name": "composition",
                    "dtype": "str",
                    "description": "Explicit framing, layout, or point of view",
                },
                {
                    "name": "medium",
                    "dtype": "str",
                    "description": "Explicit medium, in the language used by the speaker",
                },
                {
                    "name": "era",
                    "dtype": "str",
                    "description": "Explicit historical era or period",
                },
            ]
        }
    },
    "entities": ["person", "organization", "location", "product", "work_of_art"],
}


class DistillationUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class DistillationResult:
    intent: VisualIntent
    source: IntentSource


class IntentDistiller(Protocol):
    async def distill(self, transcript: str) -> DistillationResult: ...


class FixtureIntentDistiller:
    def __init__(self, projector: FastIntentProjector | None = None) -> None:
        self._projector = projector or FastIntentProjector()

    async def distill(self, transcript: str) -> DistillationResult:
        return DistillationResult(
            intent=self._projector.project(transcript),
            source="fixture",
        )


class _PioneerVisualDirection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subject: str = ""
    mood: list[str] = Field(default_factory=list)
    style: list[str] = Field(default_factory=list)
    palette: list[str] = Field(default_factory=list)
    composition: str = ""
    medium: str = ""
    era: str = ""


class _PioneerResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    visual_direction: list[_PioneerVisualDirection]


class _PioneerEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: _PioneerResult


class PioneerIntentDistiller:
    _transient_statuses = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        threshold: float,
        transport: httpx.AsyncBaseTransport | None = None,
        cache_size: int = 128,
    ) -> None:
        self._api_key = api_key
        self._url = self._native_inference_url(base_url)
        self._model = model
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_retries = max_retries
        self._threshold = threshold
        self._transport = transport
        self._cache_size = cache_size
        self._cache: OrderedDict[str, DistillationResult] = OrderedDict()

    async def distill(self, transcript: str) -> DistillationResult:
        cache_key = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache.move_to_end(cache_key)
            return cached

        body = await self._request(transcript)
        try:
            envelope = _PioneerEnvelope.model_validate(body)
            direction = envelope.result.visual_direction[0]
        except (ValidationError, IndexError) as error:
            raise DistillationUnavailable("Pioneer returned an unsupported result shape") from error

        result = DistillationResult(
            intent=VisualIntent(
                subject=direction.subject.strip(),
                moods=_clean_values(direction.mood),
                styles=_clean_values(direction.style),
                palette=_clean_values(direction.palette),
                composition=direction.composition.strip(),
                medium=direction.medium.strip().lower(),
                era=direction.era.strip(),
            ),
            source="pioneer",
        )
        self._cache[cache_key] = result
        self._cache.move_to_end(cache_key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return result

    async def _request(self, transcript: str) -> dict[str, object]:
        payload = {
            "model_id": self._model,
            "text": transcript,
            "schema": VISUAL_DIRECTION_SCHEMA,
            "threshold": self._threshold,
            "store": False,
        }
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        self._url,
                        headers={"X-API-Key": self._api_key},
                        json=payload,
                    )
                if response.status_code in self._transient_statuses and attempt < self._max_retries:
                    await asyncio.sleep(0.15 * (attempt + 1))
                    continue
                response.raise_for_status()
                parsed = response.json()
                if not isinstance(parsed, dict):
                    raise DistillationUnavailable("Pioneer returned a non-object response")
                return cast(dict[str, object], parsed)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
                last_error = error
                if attempt < self._max_retries:
                    await asyncio.sleep(0.15 * (attempt + 1))
                    continue
                break
            except ValueError as error:
                raise DistillationUnavailable("Pioneer returned invalid JSON") from error
        raise DistillationUnavailable(
            "Pioneer inference is temporarily unavailable"
        ) from last_error

    @staticmethod
    def _native_inference_url(base_url: str) -> str:
        root = base_url.rstrip("/")
        if root.endswith("/v1"):
            root = root[:-3]
        return f"{root}/inference"


@dataclass(frozen=True)
class GateDecision:
    should_discover: bool
    reasons: list[IntentChangeReason]


class DiscoveryGate:
    def __init__(self, jaccard_threshold: float) -> None:
        self._jaccard_threshold = jaccard_threshold
        self._last_triggered: VisualIntent | None = None

    def evaluate(self, intent: VisualIntent) -> GateDecision:
        previous = self._last_triggered
        if previous is None:
            self._last_triggered = intent
            return GateDecision(should_discover=True, reasons=["initial"])

        reasons: list[IntentChangeReason] = []
        if _normalized(intent.subject) != _normalized(previous.subject):
            reasons.append("subject")
        if _normalized(intent.medium) != _normalized(previous.medium):
            reasons.append("medium")
        if _normalized(intent.era) != _normalized(previous.era):
            reasons.append("era")
        if _attribute_distance(intent, previous) > self._jaccard_threshold:
            reasons.append("visual_attributes")

        if reasons:
            self._last_triggered = intent
        return GateDecision(should_discover=bool(reasons), reasons=reasons)


def build_intent_distiller(settings: Settings) -> IntentDistiller:
    if settings.demo_mode != "live" or settings.pioneer_api_key is None:
        return FixtureIntentDistiller()
    return PioneerIntentDistiller(
        api_key=settings.pioneer_api_key.get_secret_value(),
        base_url=settings.pioneer_base_url,
        model=settings.pioneer_distill_model,
        timeout_seconds=settings.pioneer_request_timeout_seconds,
        max_retries=settings.pioneer_max_retries,
        threshold=settings.pioneer_inference_threshold,
    )


def _clean_values(values: list[str]) -> list[str]:
    return sorted({value.strip().lower() for value in values if value.strip()})


def _normalized(value: str) -> str:
    return " ".join(value.lower().split())


def _attributes(intent: VisualIntent) -> set[str]:
    return {
        _normalized(value)
        for value in [*intent.moods, *intent.styles, *intent.palette]
        if _normalized(value)
    }


def _attribute_distance(left: VisualIntent, right: VisualIntent) -> float:
    left_values = _attributes(left)
    right_values = _attributes(right)
    union = left_values | right_values
    if not union:
        return 0.0
    return 1 - (len(left_values & right_values) / len(union))
