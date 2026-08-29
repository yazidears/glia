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
