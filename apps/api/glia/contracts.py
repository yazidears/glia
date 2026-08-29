from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

ExpectedLanguage = Literal["ca", "en", "es", "fr"]


def default_languages() -> list[ExpectedLanguage]:
    return ["en", "es", "ca"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictModel):
    status: str
    service: str
    mode: str
    realtime: str
    distiller: str
    image_discovery: bool = Field(
        description=(
            "Whether this server can return image candidates for a distilled intent. "
            "False means the client must not offer an image-bearing output mode."
        )
    )


class RealtimeTokenRequest(StrictModel):
    client_id: str = Field(min_length=8, max_length=128)
    languages: list[ExpectedLanguage] = Field(
        default_factory=default_languages, min_length=1, max_length=4
    )


class RealtimeTokenResponse(StrictModel):
    value: str
    expires_at: int
    model: str


class TranscriptDelta(StrictModel):
    type: Literal["transcript.delta"]
    event_id: str = Field(min_length=1, max_length=128)
    item_id: str = Field(min_length=1, max_length=128)
    delta: str = Field(min_length=1, max_length=4_000)


class TranscriptCompleted(StrictModel):
    type: Literal["transcript.completed"]
    event_id: str = Field(min_length=1, max_length=128)
    item_id: str = Field(min_length=1, max_length=128)
    transcript: str = Field(min_length=1, max_length=50_000)


class Ping(StrictModel):
    type: Literal["ping"]
    event_id: str = Field(min_length=1, max_length=128)


ClientMessage = Annotated[
    TranscriptDelta | TranscriptCompleted | Ping,
    Field(discriminator="type"),
]
client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


class VisualIntent(StrictModel):
    subject: str
    moods: list[str]
    styles: list[str]
    palette: list[str]
    composition: str = ""
    medium: str = ""
    era: str = ""


IntentSource = Literal["fixture", "local", "pioneer"]
IntentChangeReason = Literal[
    "initial",
    "subject",
    "medium",
    "era",
    "visual_attributes",
]


class SessionReady(StrictModel):
    type: Literal["session.ready"] = "session.ready"
    session_id: str
    debounce_ms: int
    heartbeat_interval_ms: int = 10_000


class TranscriptAccepted(StrictModel):
    type: Literal["transcript.accepted"] = "transcript.accepted"
    item_id: str
    transcript: str
    complete: bool


class IntentUpdated(StrictModel):
    type: Literal["intent.updated"] = "intent.updated"
    revision: int
    transcript: str
    intent: VisualIntent
    stable: bool
    source: IntentSource
    should_discover: bool = False
    change_reasons: list[IntentChangeReason] = Field(default_factory=list)


class Pong(StrictModel):
    type: Literal["pong"] = "pong"
    event_id: str


class SocketError(StrictModel):
    type: Literal["error"] = "error"
    code: str
    detail: str
    recoverable: bool


ServerMessage = SessionReady | TranscriptAccepted | IntentUpdated | Pong | SocketError


# ─── Cala discovery ─────────────────────────────────────────────────────────────
#
# Pinned to the response shape documented in docs/PARTNERS.md § 2. Cala returns NO images:
# there is no image, thumbnail, logo or media field anywhere in its schema, and nothing here
# invents one. `extra="ignore"` on the upstream models is deliberate — Cala may add fields,
# and an unknown key must not fail a demo, but no unknown key is ever read.
#
# These models parse `POST /knowledge/search` only. `POST /entities/{id}` property sources use
# a completely different `document` shape ({endpoint, params, response_hash}) and must never be
# routed through this parser.


class UpstreamModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CalaEntityHit(UpstreamModel):
    """One row of `GET /entities?name=…` — the entity-resolution step."""

    id: str
    name: str
    entity_type: str | None = None
    description: str | None = None


class CalaNamedUrl(UpstreamModel):
    name: str | None = None
    url: str | None = None


class CalaOrigin(UpstreamModel):
    source: CalaNamedUrl | None = None
    document: CalaNamedUrl | None = None


class CalaContextItem(UpstreamModel):
    id: str
    content: str = ""
    origins: list[CalaOrigin] = Field(default_factory=list)


class CalaExplanation(UpstreamModel):
    content: str = ""
    references: list[str] = Field(default_factory=list)


class CalaSearchEntity(UpstreamModel):
    id: str
    name: str
    entity_type: str | None = None
    mentions: list[str] = Field(default_factory=list)


class CalaSearchResult(UpstreamModel):
    content: str = ""
    explainability: list[CalaExplanation] = Field(default_factory=list)
    context: list[CalaContextItem] = Field(default_factory=list)
    entities: list[CalaSearchEntity] = Field(default_factory=list)


class EvidenceItem(StrictModel):
    """A `context[]` item, with the explainability join already resolved.

    `carried_answer` is ours, not Cala's: it is true when this item's id appears in some
    `explainability[].references`, which is the salience signal the UI badges.
    """

    id: str
    content: str
    origins: list[CalaOrigin]
    carried_answer: bool


class LedgerSnapshot(StrictModel):
    """Credits spent this process. `entity_calls` is counted separately because
    docs/PARTNERS.md flags it as undocumented whether `/entities` consumes credits; we charge
    it against the budget (the safe direction) while keeping it measurable against the console.
    """

    budget: int
    spent: int
    remaining: int
    search_calls: int
    entity_calls: int


DiscoveryStatus = Literal["ok", "empty", "rate_limited", "budget_exhausted"]


class DiscoverRequest(StrictModel):
    transcript: str = Field(min_length=1, max_length=50_000)
    session_id: str = Field(min_length=1, max_length=128)


class DiscoverResponse(StrictModel):
    status: DiscoveryStatus
    session_id: str
    #: The subject the naive noun-phrase heuristic pulled out of the transcript.
    subject: str | None
    #: What we actually sent to `knowledge/search`.
    query: str
    entity: CalaEntityHit | None
    answer: str | None
    explainability: list[CalaExplanation]
    context: list[EvidenceItem]
    entities: list[CalaSearchEntity]
    #: True when this response cost zero credits — a cache hit or a debounced replay.
    cached: bool
    ledger: LedgerSnapshot
    correlation_id: str


# ─── Generate ───────────────────────────────────────────────────────────────────
#
# The pin is the unit of conditioning. `image_url` is deliberately nullable and deliberately
# not optional: today's board stickers are inline SVG with no public URL, so they arrive here
# as null, and the honest consequence is that they steer the prompt as words rather than as
# reference images. Lane B tiles will carry a real https URL through the identical field.


class PinnedRef(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    lane: str = Field(min_length=1, max_length=64)
    #: Public https only. fal fetches references over the internet, so a data: URI, a blob:
    #: URL or anything on localhost is unreachable to it and is treated as no URL at all.
    image_url: str | None = Field(default=None, max_length=2_048)
    source_url: str | None = Field(default=None, max_length=2_048)


class GenerateRequest(StrictModel):
    session_id: str = Field(min_length=1, max_length=128)
    transcript: str = Field(min_length=1, max_length=50_000)
    pins: list[PinnedRef] = Field(default_factory=list, max_length=32)


class SynthesisedPrompt(StrictModel):
    """The synthesis contract, enforced on OpenAI's reply.

    A prompt that misses these bounds is a validation error here rather than a bad image later,
    which is the whole reason the model is asked for JSON instead of prose.
    """

    prompt: str = Field(min_length=12, max_length=900)

    @field_validator("prompt")
    @classmethod
    def _under_eighty_words(cls, value: str) -> str:
        words = value.split()
        if len(words) > 80:
            raise ValueError("The synthesised prompt must be under 80 words.")
        return " ".join(words)


#: `ok` carries an image. The rest are answers, not server errors — same shape, so the client
#: renders them without a second code path.
#:
#: `reference_unavailable` is the one the user can act on: fal could not fetch a pinned image,
#: and the pin is theirs to remove. It is separate from `fal_upstream_failed` because retrying
#: it never helps, and telling someone to try again when trying again cannot work is worse than
#: telling them nothing.
GenerateStatus = Literal["ok", "timeout", "already_generating", "reference_unavailable"]


class GenerateResponse(StrictModel):
    status: GenerateStatus
    session_id: str
    image_url: str | None
    #: Verbatim, exactly what was sent to fal. Empty only when we refused before synthesising.
    prompt: str
    model: str
    #: How many pins fal actually received as `image_urls`. Zero is normal and is never dressed
    #: up: the pins still reached the prompt as steering terms, which is a different claim.
    reference_count: int
    correlation_id: str
