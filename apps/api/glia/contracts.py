from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

ExpectedLanguage = Literal["ca", "en", "es", "fr"]


def default_languages() -> list[ExpectedLanguage]:
    return ["en", "es", "ca"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
