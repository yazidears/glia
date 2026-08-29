from collections.abc import Callable, Coroutine

import httpx
import pytest
from fastapi.testclient import TestClient

from glia.api import get_image_fetcher
from glia.discovery.fetch import FetchFailed, FetchRejected, ImageFetcher, host_allowed
from glia.main import app

ALLOWLIST = ("upload.wikimedia.org", "staticflickr.com")
IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Observatory.jpg"

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]


def fetcher(handler: Handler, *, max_bytes: int = 5_242_880) -> ImageFetcher:
    return ImageFetcher(
        allowlist=ALLOWLIST,
        user_agent="glia-test",
        max_bytes=max_bytes,
        connect_timeout=1,
        total_timeout=2,
        transport=httpx.MockTransport(handler),
    )


async def image_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["User-Agent"] == "glia-test"
    return httpx.Response(200, content=b"\xff\xd8pixels", headers={"content-type": "image/jpeg"})


def test_host_matching_is_on_label_boundaries() -> None:
    assert host_allowed("upload.wikimedia.org", ALLOWLIST)
    assert host_allowed("live.staticflickr.com", ALLOWLIST)
    assert not host_allowed("upload.wikimedia.org.attacker.test", ALLOWLIST)
    assert not host_allowed("evil-upload.wikimedia.org.attacker.test", ALLOWLIST)
    assert not host_allowed("notstaticflickr.com", ALLOWLIST)


@pytest.mark.parametrize(
    "url",
    [
        "http://upload.wikimedia.org/a.jpg",
        "ftp://upload.wikimedia.org/a.jpg",
        "file:///etc/passwd",
        "https://example.com/a.jpg",
        "https://127.0.0.1/a.jpg",
        "https://localhost/a.jpg",
        "https://169.254.169.254/latest/meta-data/",
        "https://upload.wikimedia.org:22/a.jpg",
        "https://user:pass@upload.wikimedia.org/a.jpg",
        "",
        f"https://upload.wikimedia.org/{'a' * 2_100}.jpg",
    ],
)
@pytest.mark.asyncio
async def test_the_fetcher_refuses_everything_outside_the_allowlist(url: str) -> None:
    with pytest.raises(FetchRejected):
        await fetcher(image_handler).open(url)


@pytest.mark.asyncio
async def test_the_fetcher_streams_an_allowed_image() -> None:
    stream = await fetcher(image_handler).open(IMAGE_URL)

    assert stream.content_type == "image/jpeg"
    assert b"".join([chunk async for chunk in stream.chunks]) == b"\xff\xd8pixels"


@pytest.mark.asyncio
async def test_the_fetcher_refuses_a_non_image_response() -> None:
    async def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})

    with pytest.raises(FetchFailed):
        await fetcher(html).open(IMAGE_URL)


@pytest.mark.asyncio
async def test_the_fetcher_refuses_a_redirect_rather_than_following_it() -> None:
    async def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://169.254.169.254/"})

    with pytest.raises(FetchFailed):
        await fetcher(redirect).open(IMAGE_URL)


@pytest.mark.asyncio
async def test_the_fetcher_refuses_an_oversized_declared_length() -> None:
    async def oversized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x" * 32,
            headers={"content-type": "image/png", "content-length": "9999999"},
        )

    with pytest.raises(FetchFailed):
        await fetcher(oversized, max_bytes=1_024).open(IMAGE_URL)


@pytest.mark.asyncio
async def test_the_byte_cap_is_enforced_while_streaming() -> None:
    async def lying(request: httpx.Request) -> httpx.Response:
        # Content-Length is attacker-controlled: it says 8, the body is 4000.
        return httpx.Response(
            200,
            content=b"x" * 4_000,
            headers={"content-type": "image/png", "content-length": "8"},
        )

    stream = await fetcher(lying, max_bytes=1_024).open(IMAGE_URL)
    body = b"".join([chunk async for chunk in stream.chunks])

    assert len(body) <= 1_024


@pytest.mark.asyncio
async def test_the_fetcher_reports_an_upstream_error() -> None:
    async def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(FetchFailed):
        await fetcher(unavailable).open(IMAGE_URL)


def test_the_proxy_route_serves_an_allowed_image() -> None:
    app.dependency_overrides[get_image_fetcher] = lambda: fetcher(image_handler)
    try:
        with TestClient(app) as client:
            response = client.get("/api/image", params={"url": IMAGE_URL})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == b"\xff\xd8pixels"


def test_the_proxy_route_rejects_a_url_we_did_not_produce() -> None:
    app.dependency_overrides[get_image_fetcher] = lambda: fetcher(image_handler)
    try:
        with TestClient(app) as client:
            response = client.get("/api/image", params={"url": "https://attacker.test/a.jpg"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "image_url_rejected"
    assert "attacker.test" not in response.text


@pytest.mark.asyncio
async def test_an_allowlisted_host_that_resolves_privately_is_still_refused() -> None:
    # Defence against DNS rebinding: the allowlist is not the only guard.
    rebound = ImageFetcher(
        allowlist=("localhost",),
        user_agent="glia-test",
        max_bytes=1_024,
        connect_timeout=1,
        total_timeout=2,
        transport=httpx.MockTransport(image_handler),
    )

    with pytest.raises(FetchRejected):
        await rebound.open("https://localhost/a.jpg")
