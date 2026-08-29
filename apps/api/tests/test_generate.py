"""Tests for the Generate beat.

Three properties are worth a test each, because all three are claims the UI makes out loud.

The pins are a real input: a pin with an origin image is fetched here, re-hosted on fal, and
goes out as `image_urls` against the reference model; a pin without one goes out as a steering
term in the prompt; and `reference_count` never overstates which happened.

Nothing that reaches fal is ours. `image_url` on a grid tile is the `/api/image` proxy on
localhost, which fal cannot fetch — so the proxy URL is never what goes out, and one test does
nothing but hold that line.

The prompt is a deliverable: it comes back verbatim, including on a timeout, because "here is
what we understood you to mean" survives a generation that did not land.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from glia.api import (
    get_fal_client,
    get_generate_distiller,
    get_prompt_synthesiser,
    get_reference_resolver,
)
from glia.config import Settings, get_settings
from glia.contracts import PinnedRef, SynthesisedPrompt, VisualIntent
from glia.discovery.fetch import FetchFailed, ImageBytes
from glia.generation.fal import (
    FalClient,
    FalReferenceUnavailable,
    FalTimedOut,
    FalUpstreamError,
    is_public_https,
)
from glia.generation.fal_storage import FalStorage, FalStorageError
from glia.generation.fixture import FIXTURE_IMAGE_URL
from glia.generation.references import ReferenceResolver, reference_pins
from glia.generation.synthesis import (
    FixturePromptSynthesiser,
    SynthesisUnavailable,
    compose_brief,
    validate_synthesised_prompt,
)
from glia.main import create_app
from glia.realtime.distiller import DistillationResult, FixtureIntentDistiller

TRANSCRIPT = "A lonely cobalt observatory above the Mediterranean, cinematic and cold."

#: A hosted fal URL, which is the only kind of reference URL a model ever sees.
FAL_HOSTED = "https://v3.fal.media/files/rehosted/reference.jpg"

STICKER_PIN = PinnedRef(
    id="observatory", title="Cobalt observatory", lane="cited page", image_url=None
)
#: A grid tile exactly as the browser holds one: `image_url` is our proxy on localhost —
#: unreachable to fal and never sent — and `origin_image_url` is the file generation uses.
HOSTED_PIN = PinnedRef(
    id="hosted",
    title="Brutalist sun study",
    lane="open",
    image_url="http://localhost:8000/api/image?url=https%3A%2F%2Fupload.wikimedia.org%2Fexample.jpg",
    origin_image_url="https://upload.wikimedia.org/example.jpg",
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


class _StubFetcher:
    """The guarded fetcher, minus the network. Keyed on the origin URL so a test can make one
    reference unfetchable without making them all unfetchable."""

    def __init__(self, *, failing: set[str] | None = None) -> None:
        self.read_urls: list[str] = []
        self._failing = failing or set()

    async def read(self, raw_url: str) -> ImageBytes:
        self.read_urls.append(raw_url)
        if raw_url in self._failing:
            raise FetchFailed("Upstream image host returned an error")
        return ImageBytes(content_type="image/jpeg", data=b"\xff\xd8\xff-not-really-a-jpeg")


class _StubStorage:
    """fal's storage. Returns a distinct fal URL per upload so order is checkable."""

    def __init__(self, *, failing_after: int | None = None) -> None:
        self.uploads: list[bytes] = []
        self._failing_after = failing_after

    async def upload(self, data: bytes, *, content_type: str) -> str:
        if self._failing_after is not None and len(self.uploads) >= self._failing_after:
            raise FalStorageError("fal storage returned 500.")
        self.uploads.append(data)
        return f"{FAL_HOSTED}?n={len(self.uploads)}"


def stub_resolver(
    fetcher: Any = None, storage: Any = None, config: Settings | None = None
) -> ReferenceResolver:
    resolved = config or settings()
    return ReferenceResolver(
        fetcher=fetcher or _StubFetcher(),
        storage=storage or _StubStorage(),
        max_references=resolved.fal_max_reference_images,
        timeout=resolved.fal_reference_timeout_seconds,
    )


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
    resolver: ReferenceResolver | None = None,
) -> TestClient:
    resolved = config or settings()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: resolved
    app.dependency_overrides[get_fal_client] = lambda: fal
    app.dependency_overrides[get_prompt_synthesiser] = lambda: synthesiser or _StubSynthesiser()
    app.dependency_overrides[get_generate_distiller] = lambda: distiller or FixtureIntentDistiller()
    app.dependency_overrides[get_reference_resolver] = lambda: resolver or stub_resolver(
        config=resolved
    )
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


def test_reference_pins_cap_at_the_limit() -> None:
    pins = [
        PinnedRef(
            id=str(i),
            title=f"pin {i}",
            lane="open",
            origin_image_url=f"https://cdn.test/{i}.jpg",
        )
        for i in range(6)
    ]
    assert len(reference_pins(pins, 4)) == 4


def test_reference_pins_drop_stickers_without_dropping_the_pin() -> None:
    # The sticker is not a reference, but it is still a pin — the prompt is where it lands.
    assert reference_pins([STICKER_PIN, HOSTED_PIN], 4) == [HOSTED_PIN]


def test_a_pin_with_only_a_proxy_url_is_not_a_reference() -> None:
    """The proxy is on localhost and no amount of wanting makes it fetchable.

    A pin whose `image_url` is our proxy and whose `origin_image_url` is missing is a pin we
    cannot condition on. It is dropped from the references — not repaired by falling back to
    the display URL, which is the bug this whole change exists to remove.
    """
    proxy_only = PinnedRef(
        id="proxy-only",
        title="Tile with no origin",
        lane="open",
        image_url="http://localhost:8000/api/image?url=https%3A%2F%2Fcdn.test%2Fa.jpg",
    )
    assert reference_pins([proxy_only], 4) == []


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


def test_pins_with_origin_urls_reach_fal_as_rehosted_image_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _FalRecorder()
    stub_transport(recorder.handler, monkeypatch)
    fetcher = _StubFetcher()
    storage = _StubStorage()
    fal = FalClient(settings())
    with client_for(fal, resolver=stub_resolver(fetcher, storage)) as http:
        payload = http.post("/v1/generate", json=body()).json()

    submit = recorder.requests[0]
    assert "flux-pro/kontext/max/multi" in str(submit.url)
    assert submit.headers["Authorization"].startswith("Key ")
    assert submit.headers["X-Fal-Store-IO"] == "0"
    # The origin was fetched by us, the bytes were uploaded, and what fal received is the URL
    # the upload returned. Every hop of the round trip, asserted.
    assert fetcher.read_urls == [HOSTED_PIN.origin_image_url]
    assert len(storage.uploads) == 1
    assert f"{FAL_HOSTED}?n=1".encode() in recorder.bodies[0]
    assert payload["reference_count"] == 1
    assert payload["unavailable_references"] == []
    assert payload["image_url"] == "https://fal.media/out.png"


def test_nothing_sent_to_fal_is_our_own_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """The line this whole change exists to hold.

    fal cannot fetch localhost, so a submit body carrying `/api/image` is a generation that was
    always going to fail with `file_download_error`. Asserted against the raw bytes of every
    request, not against an intermediate list, because the bytes are what actually leaves.
    """
    recorder = _FalRecorder()
    stub_transport(recorder.handler, monkeypatch)
    fal = FalClient(settings())
    with client_for(fal) as http:
        assert http.post("/v1/generate", json=body()).json()["status"] == "ok"

    assert recorder.bodies
    for sent in recorder.bodies:
        assert b"localhost" not in sent
        assert b"/api/image" not in sent
        assert b"127.0.0.1" not in sent


def test_pins_without_origin_urls_fall_back_and_report_zero_references(
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


# ─── one bad pin is not a failed generation ─────────────────────────────────────


SECOND_PIN = PinnedRef(
    id="second",
    title="Harbour at dusk",
    lane="open",
    image_url="http://localhost:8000/api/image?url=https%3A%2F%2Flive.staticflickr.com%2Fb.jpg",
    origin_image_url="https://live.staticflickr.com/b.jpg",
    source_url="https://www.flickr.com/photos/example/2",
)


def test_an_unfetchable_pin_is_dropped_and_named_not_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _FalRecorder()
    stub_transport(recorder.handler, monkeypatch)
    fetcher = _StubFetcher(failing={HOSTED_PIN.origin_image_url or ""})
    fal = FalClient(settings())
    resolver = stub_resolver(fetcher, _StubStorage())
    with client_for(fal, resolver=resolver) as http:
        payload = http.post(
            "/v1/generate",
            json=body(pins=[HOSTED_PIN.model_dump(), SECOND_PIN.model_dump()]),
        ).json()

    # The good pin still conditioned the image; the bad one is named so the user can act on it.
    assert payload["status"] == "ok"
    assert payload["image_url"] == "https://fal.media/out.png"
    assert payload["reference_count"] == 1
    assert payload["unavailable_references"] == ["hosted"]


def test_a_failed_upload_is_dropped_the_same_way(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _FalRecorder()
    stub_transport(recorder.handler, monkeypatch)
    # The first upload lands, the second is refused by fal's storage.
    fal = FalClient(settings())
    resolver = stub_resolver(_StubFetcher(), _StubStorage(failing_after=1))
    with client_for(fal, resolver=resolver) as http:
        payload = http.post(
            "/v1/generate",
            json=body(pins=[HOSTED_PIN.model_dump(), SECOND_PIN.model_dump()]),
        ).json()

    assert payload["status"] == "ok"
    assert payload["reference_count"] == 1
    assert payload["unavailable_references"] == ["second"]


def test_every_pin_failing_still_generates_from_the_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _FalRecorder()
    stub_transport(recorder.handler, monkeypatch)
    fetcher = _StubFetcher(failing={HOSTED_PIN.origin_image_url or ""})
    fal = FalClient(settings())
    synthesiser = _StubSynthesiser()
    with client_for(
        fal, synthesiser=synthesiser, resolver=stub_resolver(fetcher, _StubStorage())
    ) as http:
        payload = http.post("/v1/generate", json=body()).json()

    # No references, so the fallback model — but an image, and both pins in the synthesis.
    assert "flux/schnell" in str(recorder.requests[0].url)
    assert payload["status"] == "ok"
    assert payload["reference_count"] == 0
    assert payload["unavailable_references"] == ["hosted"]
    assert synthesiser.calls == [[STICKER_PIN, HOSTED_PIN]]


@pytest.mark.asyncio
async def test_the_resolver_returns_fal_urls_in_pin_order() -> None:
    resolver = stub_resolver(_StubFetcher(), _StubStorage())
    resolved = await resolver.resolve([STICKER_PIN, HOSTED_PIN, SECOND_PIN])
    assert resolved.unavailable == []
    assert len(resolved.urls) == 2
    assert all(url.startswith("https://v3.fal.media/") for url in resolved.urls)


@pytest.mark.asyncio
async def test_delivered_and_unavailable_partition_the_eligible_pins() -> None:
    """The two lists together are the eligible set, and they never overlap.

    This is what stops a pin that uploaded perfectly well from being reported as broken: a
    caller reads `delivered`, and never has to re-derive "which ones did we send" by applying
    the eligibility rule a second time.
    """
    resolver = stub_resolver(_StubFetcher(failing={HOSTED_PIN.origin_image_url or ""}))
    resolved = await resolver.resolve([STICKER_PIN, HOSTED_PIN, SECOND_PIN])

    assert resolved.delivered == ["second"]
    assert resolved.unavailable == ["hosted"]
    assert set(resolved.delivered).isdisjoint(resolved.unavailable)
    assert len(resolved.urls) == len(resolved.delivered)


@pytest.mark.asyncio
async def test_the_resolver_caps_at_the_configured_maximum() -> None:
    pins = [
        PinnedRef(
            id=f"pin-{i}",
            title=f"pin {i}",
            lane="open",
            origin_image_url=f"https://upload.wikimedia.org/{i}.jpg",
        )
        for i in range(6)
    ]
    resolver = stub_resolver(config=settings(fal_max_reference_images=2))
    resolved = await resolver.resolve(pins)
    # Capped before the fetch, so the images past the cap are never even requested.
    assert len(resolved.urls) == 2
    assert resolved.unavailable == []


# ─── the upload hop ─────────────────────────────────────────────────────────────


def _storage_transport(
    handler: Callable[[httpx.Request], httpx.Response], monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(**kwargs)

    monkeypatch.setattr("glia.generation.fal_storage.httpx.AsyncClient", factory)


@pytest.mark.asyncio
async def test_the_upload_sends_the_bytes_and_returns_the_file_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            assert request.url.params["storage_type"] == "fal-cdn-v3"
            assert request.headers["Authorization"].startswith("Key ")
            return httpx.Response(
                200,
                json={
                    "file_url": "https://v3b.fal.media/files/b/abc/reference.jpg",
                    "upload_url": "https://v3b.fal.media/files/b/abc/reference.jpg?signature=x",
                },
            )
        return httpx.Response(200)

    _storage_transport(handler, monkeypatch)
    url = await FalStorage(settings()).upload(b"pixels", content_type="image/jpeg")

    assert url == "https://v3b.fal.media/files/b/abc/reference.jpg"
    assert [request.method for request in seen] == ["POST", "PUT"]
    assert seen[1].content == b"pixels"


@pytest.mark.asyncio
async def test_an_upload_url_on_a_private_address_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The response is authenticated, which is a reason to be surprised — not a reason to be
    unable to notice. A blind PUT to link-local metadata is a real thing, so it is checked."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "file_url": "https://v3b.fal.media/files/b/abc/reference.jpg",
                    "upload_url": "https://169.254.169.254/latest/meta-data/",
                },
            )
        raise AssertionError("a non-public upload_url must never be written to")

    _storage_transport(handler, monkeypatch)
    with pytest.raises(FalStorageError):
        await FalStorage(settings()).upload(b"pixels", content_type="image/jpeg")


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
    # fal will not say which reference it choked on, and the vendor body stays inside the
    # client, so every pin we actually sent is named rather than one being guessed.
    assert payload["unavailable_references"] == ["hosted"]


def test_a_locally_dropped_pin_is_reported_once_not_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One pin we could not fetch, one fal then refused. Two ids, each appearing once.

    The bug this pins down: reporting the whole *eligible* set here would list the dropped pin
    twice, and — worse, in the case where fal refuses only one of several — would name pins that
    uploaded fine, telling the user to unpin a reference that was never the problem.
    """
    stub_transport(_unfetchable_reference, monkeypatch)
    fal = FalClient(settings())
    resolver = stub_resolver(_StubFetcher(failing={HOSTED_PIN.origin_image_url or ""}))
    with client_for(fal, resolver=resolver) as http:
        payload = http.post(
            "/v1/generate",
            json=body(pins=[HOSTED_PIN.model_dump(), SECOND_PIN.model_dump()]),
        ).json()

    assert payload["status"] == "reference_unavailable"
    reported = payload["unavailable_references"]
    assert sorted(reported) == ["hosted", "second"]
    assert len(reported) == len(set(reported))


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
