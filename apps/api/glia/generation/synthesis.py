"""Step (a) of Generate: transcript + distilled intent + pin titles + grounding → one prompt.

The prompt this returns is a deliverable, not an internal. It is shown to the user verbatim
beside the image, which is the reason the output is constrained by a Pydantic schema rather
than trusted: a prompt we cannot show is a prompt we do not send.

The raw transcript never leaves this module. Summarising it is the entire point of the step —
speech is personal, and fal receives the summary, never the speech.

Grounding is the fourth input and the only optional one: the passages Cala cited about the
subject, so the prompt can say what the thing actually looks like rather than only how it felt
to describe. It is deliberately subordinate — the speaker owns the mood, the style and the
palette, and research that overrode those would be answering a question nobody asked. Absent
grounding changes nothing, which is what makes it safe to send from a lane that can fail.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

import structlog
from pydantic import ValidationError

from glia.config import Settings
from glia.contracts import PinnedRef, SynthesisedPrompt, VisualIntent

if TYPE_CHECKING:
    from openai import OpenAI

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "You write image prompts. You are given a person's spoken thinking, the visual attributes "
    "distilled from it, and the titles of the references they pinned. Return ONE prompt for a "
    "text-to-image model, under 80 words, naming the subject, mood, style, palette and "
    "composition. Treat the pinned titles as visual steering: fold their qualities into the "
    "prompt. You may also be given grounding: passages from a knowledge API about the subject. "
    "Use grounding only for visual specificity — what the subject looks like, its materials, "
    "setting and period. Never let grounding override the speaker's mood, style or palette, "
    "never name a source, and never assert a fact an image cannot show. "
    "Write only the prompt itself — no preamble, no quotes, no options, no commentary."
)

#: How much of one cited passage the brief carries. Cala returns paragraphs; the prompt is
#: capped at 80 words, so the tail of a passage cannot reach the image and would only crowd the
#: speaker's own words out of the model's attention.
GROUNDING_CHARACTERS = 600

#: The brief carries at most this many passages, in the order the caller sent them — the answer
#: first, then the context items Cala's own explainability said carried it.
MAX_GROUNDING_NOTES = 3


class SynthesisUnavailable(RuntimeError):
    """No OpenAI key, or OpenAI did not return a prompt we are willing to show."""


class PromptSynthesiser(Protocol):
    async def synthesise(
        self,
        transcript: str,
        intent: VisualIntent,
        pins: list[PinnedRef],
        grounding: Sequence[str] = (),
    ) -> str: ...


def compose_brief(
    transcript: str,
    intent: VisualIntent,
    pins: list[PinnedRef],
    grounding: Sequence[str] = (),
) -> str:
    """The user-side half of the synthesis call, also the fixture's raw material."""
    lines = [f"Spoken thinking: {transcript.strip()}"]
    attributes = [
        ("Subject", intent.subject),
        ("Mood", ", ".join(intent.moods)),
        ("Style", ", ".join(intent.styles)),
        ("Palette", ", ".join(intent.palette)),
        ("Composition", intent.composition),
        ("Medium", intent.medium),
        ("Era", intent.era),
    ]
    lines.extend(f"{label}: {value}" for label, value in attributes if value)
    if pins:
        lines.append("Pinned references: " + "; ".join(pin.title for pin in pins))
    notes = [clipped for note in grounding[:MAX_GROUNDING_NOTES] if (clipped := _clip(note))]
    if notes:
        # Labelled, and labelled last. The order is part of the instruction: the model reads the
        # speaker before it reads the research, and the label says which of the two is in charge.
        lines.append("Grounding (research on the subject — visual specificity only):")
        lines.extend(f"- {note}" for note in notes)
    return "\n".join(lines)


def _clip(note: str) -> str:
    """Trim one passage to the brief's budget, at a word boundary where there is one."""
    note = " ".join(note.split())
    if len(note) <= GROUNDING_CHARACTERS:
        return note
    head = note[:GROUNDING_CHARACTERS]
    cut = head.rfind(" ")
    return (head[:cut] if cut > GROUNDING_CHARACTERS // 2 else head).rstrip(" ,;:") + "\u2026"


class FixturePromptSynthesiser:
    """Deterministic, offline, and shaped like the real thing.

    `demo_mode="fixture"` has to hold with the network unplugged, so this composes the prompt
    from the same inputs by hand instead of asking for one.

    Grounding is accepted and ignored, deliberately. Every other input is a bounded field whose
    contribution to the 80-word cap can be reasoned about; grounding is free prose from an
    upstream body, and a fixture that could fail its own contract on a long passage is not a
    fixture. Compressing it needs the model the live path has and this one does not.
    """

    async def synthesise(
        self,
        transcript: str,
        intent: VisualIntent,
        pins: list[PinnedRef],
        grounding: Sequence[str] = (),
    ) -> str:
        subject = intent.subject or _leading_clause(transcript)
        clauses = [subject]
        for values in (intent.styles, intent.moods, intent.palette):
            if values:
                clauses.append(", ".join(values))
        if intent.composition:
            clauses.append(intent.composition)
        if intent.medium:
            clauses.append(f"as a {intent.medium}")
        if intent.era:
            clauses.append(intent.era)
        if pins:
            clauses.append("echoing " + ", ".join(pin.title.lower() for pin in pins))
        prompt = ", ".join(clause for clause in clauses if clause)
        # Same gate as the live path: the fixture is not exempt from the contract it stands in
        # for, and a fixture that could not be shown would be a lie about the live behaviour.
        return SynthesisedPrompt(prompt=_pad(prompt)).prompt


class OpenAIPromptSynthesiser:
    """One ordinary chat completion against `OPENAI_SYNTHESIS_MODEL`.

    JSON schema on the way out, Pydantic on the way back. Neither alone is enough: the schema
    is what the model is asked for, the validator is what we are willing to show.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def synthesise(
        self,
        transcript: str,
        intent: VisualIntent,
        pins: list[PinnedRef],
        grounding: Sequence[str] = (),
    ) -> str:
        api_key = self._settings.openai_api_key
        if api_key is None or not api_key.get_secret_value():
            raise SynthesisUnavailable("OPENAI_API_KEY is not configured")

        brief = compose_brief(transcript, intent, pins, grounding)
        timeout = self._settings.openai_request_timeout_seconds

        def call() -> str:
            client = _client(api_key.get_secret_value(), timeout)
            completion = client.chat.completions.create(
                model=self._settings.openai_synthesis_model,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": brief},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "synthesised_prompt",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {"prompt": {"type": "string"}},
                            "required": ["prompt"],
                            "additionalProperties": False,
                        },
                    },
                },
            )
            content = completion.choices[0].message.content
            if not content:
                raise SynthesisUnavailable("OpenAI returned an empty synthesis")
            return content

        try:
            raw = await asyncio.wait_for(asyncio.to_thread(call), timeout=timeout + 2)
        except SynthesisUnavailable:
            raise
        except TimeoutError as error:
            raise SynthesisUnavailable("Prompt synthesis timed out") from error
        except Exception as error:
            # The vendor body is a vendor body: logged by type, never returned.
            logger.warning("generate.synthesis.failed", error=type(error).__name__)
            raise SynthesisUnavailable("Prompt synthesis failed") from error

        return validate_synthesised_prompt(raw)


def validate_synthesised_prompt(raw: str) -> str:
    """The gate the model's reply has to pass before anyone sees it or fal receives it."""
    try:
        payload = json.loads(raw)
    except ValueError as error:
        raise SynthesisUnavailable("Prompt synthesis returned invalid JSON") from error
    try:
        return SynthesisedPrompt.model_validate(payload).prompt
    except ValidationError as error:
        # Deliberately fatal. An 80-word cap that silently truncates is not a cap, and a prompt
        # we altered after the model wrote it is no longer the prompt we can show verbatim.
        raise SynthesisUnavailable("Prompt synthesis broke its schema") from error


def _client(api_key: str, timeout: float) -> OpenAI:
    # Lazy, as in `realtime/token.py`: nothing that does not synthesise pays the import.
    from openai import OpenAI

    return OpenAI(api_key=api_key, timeout=timeout, max_retries=1)


def _leading_clause(transcript: str) -> str:
    words = transcript.split()
    return " ".join(words[:16])


def _pad(prompt: str) -> str:
    """The schema's 12-character floor is a real floor. A near-silent session distils to almost
    nothing, and the fixture must still produce something showable rather than fail the demo."""
    return prompt if len(prompt) >= 12 else f"{prompt} an unfinished idea, softly lit".strip()


def build_prompt_synthesiser(settings: Settings) -> PromptSynthesiser:
    if settings.demo_mode != "live" or settings.openai_api_key is None:
        return FixturePromptSynthesiser()
    return OpenAIPromptSynthesiser(settings)
