"""Tests for the Generate beat.

Two properties are worth a test each, because both are claims the UI makes out loud.

The pins are a real input: a pin fal can fetch goes out as `image_urls` against the reference
model, a pin it cannot goes out as a steering term in the prompt, and `reference_count` never
overstates which happened.

The prompt is a deliverable: it comes back verbatim, including on a timeout, because "here is
what we understood you to mean" survives a generation that did not land.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from glia.api import get_fal_client, get_generate_distiller, get_prompt_synthesiser
from glia.config import Settings, get_settings
from glia.contracts import PinnedRef, SynthesisedPrompt, VisualIntent
from glia.generation.fal import (
    FalClient,
    FalReferenceUnavailable,
    FalTimedOut,
    FalUpstreamError,
    is_public_https,
    reference_urls,
)
from glia.generation.fixture import FIXTURE_IMAGE_URL
from glia.generation.synthesis import (
    FixturePromptSynthesiser,
    SynthesisUnavailable,
    compose_brief,
    validate_synthesised_prompt,
)
from glia.main import create_app
from glia.realtime.distiller import DistillationResult, FixtureIntentDistiller

TRANSCRIPT = "A lonely cobalt observatory above the Mediterranean, cinematic and cold."

STICKER_PIN = PinnedRef(
    id="observatory", title="Cobalt observatory", lane="cited page", image_url=None
)
HOSTED_PIN = PinnedRef(
    id="hosted",
    title="Brutalist sun study",
    lane="open",
    image_url="https://upload.wikimedia.org/example.jpg",
    source_url="https://commons.wikimedia.org/wiki/File:Example.jpg",
)


def settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "fal_key": "test-key-not-a-real-credential",
        "fal_poll_interval_seconds": 0.01,
        "fal_poll_timeout_seconds": 0.5,
        "demo_mode": "live",
    }
    base.update(overrides)
    return Settings(**base)


class _StubSynthesiser:
    def __init__(self, prompt: str = "a cobalt observatory over a cold sea") -> None:
        self.prompt = prompt
        self.calls: list[list[PinnedRef]] = []

    async def synthesise(
        self, transcript: str, intent: VisualIntent, pins: list[PinnedRef]
    ) -> str:
        self.calls.append(pins)
        return self.prompt


class _FalRecorder:
    """Stands in for the fal queue. Records every request so a test can prove there was one."""

    def __init__(self, *, stall: bool = False) -> None:
        self.requests: list[httpx.Request] = []
        self.bodies: list[Any] = []
        self.stall = stall

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "POST":
            self.bodies.append(request.content)
            return httpx.Response(
                200,
                json={
                    "request_id": "req-1",
                    "status_url": "https://queue.fal.run/fal-ai/flux/requests/req-1/status",
                    "response_url": "https://queue.fal.run/fal-ai/flux/requests/req-1",
                },
            )
        if path.endswith("/status"):
            return httpx.Response(200, json={"status": "IN_QUEUE" if self.stall else "COMPLETED"})
        return httpx.Response(200, json={"images": [{"url": "https://fal.media/out.png"}]})


def stub_transport(
    handler: Callable[[httpx.Request], httpx.Response], monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(**kwargs)

    monkeypatch.setattr("glia.generation.fal.httpx.AsyncClient", factory)


def client_for(
    fal: FalClient,
    config: Settings | None = None,
    synthesiser: Any = None,
    distiller: Any = None,
) -> TestClient:
    resolved = config or settings()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: resolved
    app.dependency_overrides[get_fal_client] = lambda: fal
    app.dependency_overrides[get_prompt_synthesiser] = lambda: synthesiser or _StubSynthesiser()
    app.dependency_overrides[get_generate_distiller] = lambda: distiller or FixtureIntentDistiller()
    return TestClient(app)


def body(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_id": "session-1",
        "transcript": TRANSCRIPT,
        "pins": [STICKER_PIN.model_dump(), HOSTED_PIN.model_dump()],
    }
    payload.update(overrides)
    return payload


# ─── what counts as a reference ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "usable"),
    [
        ("https://upload.wikimedia.org/a.jpg", True),
        ("http://upload.wikimedia.org/a.jpg", False),
        ("https://localhost/a.jpg", False),
        ("https://127.0.0.1/a.jpg", False),
        ("https://10.0.0.4/a.jpg", False),
        ("data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=", False),
        (None, False),
    ],
)
def test_is_public_https(url: str | None, usable: bool) -> None:
    assert is_public_https(url) is usable


def test_reference_urls_caps_at_the_limit() -> None:
    pins = [
        PinnedRef(id=str(i), title=f"pin {i}", lane="open", image_url=f"https://cdn.test/{i}.jpg")
        for i in range(6)
    ]
    assert len(reference_urls(pins, 4)) == 4


def test_reference_urls_drops_stickers_without_dropping_the_pin() -> None:
    # The sticker is not a reference, but it is still a pin — the prompt is where it lands.
    assert reference_urls([STICKER_PIN, HOSTED_PIN], 4) == [HOSTED_PIN.image_url]


# ─── the prompt is a deliverable ────────────────────────────────────────────────


def test_synthesis_schema_rejects_an_over_long_prompt() -> None:
    with pytest.raises(ValidationError):
        SynthesisedPrompt(prompt=" ".join(["word"] * 81))


def test_synthesis_schema_normalises_whitespace() -> None:
    assert SynthesisedPrompt(prompt="  a  cobalt   observatory  ").prompt == "a cobalt observatory"


def test_malformed_synthesis_is_a_refusal_not_a_generation() -> None:
    # A prompt we cannot show is a prompt we do not send.
    with pytest.raises(SynthesisUnavailable):
        validate_synthesised_prompt('{"prompt": "hi"}')


def test_compose_brief_carries_pin_titles_into_the_synthesis() -> None:
    intent = VisualIntent(
        subject="observatory", moods=["cold"], styles=[], palette=["cobalt"], composition=""
    )
    brief = compose_brief(TRANSCRIPT, intent, [STICKER_PIN])
    assert "Cobalt observatory" in brief
    assert "Pinned references" in brief


@pytest.mark.asyncio
async def test_fixture_synthesis_folds_unfetchable_pins_into_the_prompt() -> None:
    result = await FixtureIntentDistiller().distill(TRANSCRIPT)
    prompt = await FixturePromptSynthesiser().synthesise(TRANSCRIPT, result.intent, [STICKER_PIN])
    assert "cobalt observatory" in prompt.lower()


# ─── the route ──────────────────────────────────────────────────────────────────


def test_fixture_mode_returns_a_canned_result_without_a_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(**kwargs: Any) -> httpx.AsyncClient:
        raise AssertionError("fixture mode must not open a connection")

    monkeypatch.setattr("glia.generation.fal.httpx.AsyncClient", refuse)
    config = settings(demo_mode="fixture")
    fal = FalClient(config)
    with client_for(fal, config, synthesiser=FixturePromptSynthesiser()) as http:
        payload = http.post("/v1/generate", json=body()).json()

    assert payload["status"] == "ok"
    assert payload["image_url"] == FIXTURE_IMAGE_URL
    assert payload["model"].startswith("fixture:")
    assert payload["prompt"]


def test_pins_with_public_urls_reach_fal_as_image_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _FalRecorder()
    stub_transport(recorder.handler, monkeypatch)
    fal = FalClient(settings())
    with client_for(fal) as http:
        payload = http.post("/v1/generate", json=body()).json()

    submit = recorder.requests[0]
    assert "flux-pro/kontext/max/multi" in str(submit.url)
    assert submit.headers["Authorization"].startswith("Key ")
    assert submit.headers["X-Fal-Store-IO"] == "0"
    assert HOSTED_PIN.image_url is not None
    assert HOSTED_PIN.image_url.encode() in recorder.bodies[0]
    assert payload["reference_count"] == 1
    assert payload["image_url"] == "https://fal.media/out.png"


def test_pins_without_public_urls_fall_back_and_report_zero_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _FalRecorder()
    stub_transport(recorder.handler, monkeypatch)
    synthesiser = _StubSynthesiser()
    fal = FalClient(settings())
    with client_for(fal, synthesiser=synthesiser) as http:
        payload = http.post(
            "/v1/generate", json=body(pins=[STICKER_PIN.model_dump()])
        ).json()

    assert "flux/schnell" in str(recorder.requests[0].url)
    assert b"image_urls" not in recorder.bodies[0]
    # Zero references, and the pin still went into the synthesis. Both halves of the honest
    # story: it steered the prompt, it did not condition the image.
    assert payload["reference_count"] == 0
    assert synthesiser.calls == [[STICKER_PIN]]


def test_a_second_generation_is_refused_not_queued(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_transport(_FalRecorder().handler, monkeypatch)
    fal = FalClient(settings())
    # The first click is still in flight; fal allows two concurrent requests account-wide, so
    # the second click has to be told no rather than silently spending another generation.
    fal.acquire("session-1")
    with client_for(fal) as http:
        payload = http.post("/v1/generate", json=body()).json()

    assert payload["status"] == "already_generating"
    assert payload["image_url"] is None


def test_the_slot_is_released_so_the_next_click_works(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_transport(_FalRecorder().handler, monkeypatch)
    fal = FalClient(settings())
    with client_for(fal) as http:
        assert http.post("/v1/generate", json=body()).json()["status"] == "ok"
        assert http.post("/v1/generate", json=body()).json()["status"] == "ok"


def test_a_timeout_is_typed_and_still_carries_the_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_transport(_FalRecorder(stall=True).handler, monkeypatch)
    fal = FalClient(settings())
    synthesiser = _StubSynthesiser()
    with client_for(fal, synthesiser=synthesiser) as http:
        payload = http.post("/v1/generate", json=body()).json()

    assert payload["status"] == "timeout"
    assert payload["image_url"] is None
    assert payload["prompt"] == synthesiser.prompt


def test_a_broken_synthesis_never_reaches_fal(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _FalRecorder()
    stub_transport(recorder.handler, monkeypatch)

    class _Broken:
        async def synthesise(
            self, transcript: str, intent: VisualIntent, pins: list[PinnedRef]
        ) -> str:
            raise SynthesisUnavailable("no prompt")

    fal = FalClient(settings())
    with client_for(fal, synthesiser=_Broken()) as http:
        response = http.post("/v1/generate", json=body())

    assert response.status_code == 502
    assert response.json()["code"] == "synthesis_failed"
    assert recorder.requests == []


def test_submit_is_never_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts.append(request)
            return httpx.Response(500, json={"detail": "boom"})
        raise AssertionError("nothing should be polled after a failed submit")

    stub_transport(handler, monkeypatch)
    fal = FalClient(settings())
    with client_for(fal) as http:
        assert http.post("/v1/generate", json=body()).status_code == 502
    # A retried submit is a second billed generation for one click.
    assert len(posts) == 1


def test_a_forged_status_url_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request_id": "req-1",
                "status_url": "https://attacker.test/status",
                "response_url": "https://attacker.test/result",
            },
        )

    stub_transport(handler, monkeypatch)
    fal = FalClient(settings())
    with client_for(fal) as http:
        assert http.post("/v1/generate", json=body()).status_code == 502


@pytest.mark.asyncio
async def test_fal_timeout_is_its_own_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_transport(_FalRecorder(stall=True).handler, monkeypatch)
    fal = FalClient(settings())
    with pytest.raises(FalTimedOut):
        await fal.generate(model="fal-ai/flux/schnell", prompt="a cold sea", references=[])


@pytest.mark.asyncio
async def test_distiller_failure_still_produces_an_intent() -> None:
    result = await FixtureIntentDistiller().distill(TRANSCRIPT)
    assert isinstance(result, DistillationResult)
    assert result.intent.subject


# ─── a reference fal cannot fetch ───────────────────────────────────────────────
#
# Measured against the live API on 29 Aug 2026. fal marks such a request COMPLETED on the
# status endpoint and only rejects it from the *result* endpoint, with a 422 carrying
# `detail[].type == "file_download_error"`. Both halves of that are load-bearing, so both are
# pinned here — a status poll that believed COMPLETED and a result fetch that read the 422 as a
# generic upstream error is exactly the bug this replaced.

_DOWNLOAD_FAILURE: dict[str, Any] = {
    "detail": [
        {
            "loc": ["body", "image_urls"],
            "msg": "Failed to download the file.",
            "type": "file_download_error",
            "input": ["https://upload.wikimedia.org/example.jpg"],
        }
    ]
}


def _unfetchable_reference(request: httpx.Request) -> httpx.Response:
    if request.method == "POST":
        return httpx.Response(
            200,
            json={
                "request_id": "req-1",
                "status_url": "https://queue.fal.run/fal-ai/flux-pro/requests/req-1/status",
                "response_url": "https://queue.fal.run/fal-ai/flux-pro/requests/req-1",
            },
        )
    if request.url.path.endswith("/status"):
        # fal really does say COMPLETED here for a request it rejected.
        return httpx.Response(200, json={"status": "COMPLETED"})
    return httpx.Response(422, json=_DOWNLOAD_FAILURE)


def test_an_unfetchable_reference_is_its_own_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_transport(_unfetchable_reference, monkeypatch)
    fal = FalClient(settings())
    synthesiser = _StubSynthesiser()
    with client_for(fal, synthesiser=synthesiser) as http:
        response = http.post("/v1/generate", json=body())

    payload = response.json()
    # A 200 with a typed status, not a 502: retrying cannot help, and the prompt is still worth
    # showing. The reference count reports what we tried to send, not what fal accepted.
    assert response.status_code == 200
    assert payload["status"] == "reference_unavailable"
    assert payload["image_url"] is None
    assert payload["prompt"] == synthesiser.prompt
    assert payload["reference_count"] == 1


@pytest.mark.asyncio
async def test_unfetchable_reference_is_not_a_generic_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_transport(_unfetchable_reference, monkeypatch)
    fal = FalClient(settings())
    with pytest.raises(FalReferenceUnavailable):
        await fal.generate(
            model="fal-ai/flux-pro/kontext/max/multi",
            prompt="a cold sea",
            references=["https://upload.wikimedia.org/example.jpg"],
        )


@pytest.mark.asyncio
async def test_an_ordinary_422_is_still_an_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(422, json={"detail": [{"type": "value_error", "loc": []}]})
        raise AssertionError("a rejected submit is never polled")

    stub_transport(handler, monkeypatch)
    fal = FalClient(settings())
    with pytest.raises(FalUpstreamError):
        await fal.generate(model="fal-ai/flux/schnell", prompt="a cold sea", references=[])
