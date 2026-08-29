import json
from collections.abc import Callable, Coroutine

import httpx
import pytest

from glia.discovery.commons import CommonsLane
from glia.discovery.lane import LaneUnavailable
from glia.discovery.openverse import OpenverseLane

OPENVERSE_RESULT = {
    "id": "abc-123",
    "title": "Doane Observatory",
    "url": "https://live.staticflickr.com/65535/54215711139_50a325407d_b.jpg",
    "foreign_landing_url": "https://www.flickr.com/photos/59081381@N03/54215711139",
    "source": "flickr",
    "license": "by-sa",
    "license_version": "2.0",
    "width": 1024,
    "height": 768,
}

COMMONS_PAGE = {
    "pageid": 182355926,
    "index": 1,
    "title": "File:Assy-Turgen_Observatory.jpg",
    "imageinfo": [
        {
            "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/64/x.jpg/800px-x.jpg",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Assy-Turgen_Observatory.jpg",
            "thumbwidth": 800,
            "thumbheight": 910,
            "extmetadata": {
                "LicenseShortName": {"value": "CC BY-SA 4.0", "source": "commons-desc-page"},
                "ObjectName": {"value": "Assy-Turgen Observatory", "source": "commons-desc-page"},
            },
        }
    ],
}


Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]


def openverse_lane(
    handler: Handler, *, client_id: str | None = None, client_secret: str | None = None
) -> OpenverseLane:
    return OpenverseLane(
        base_url="https://api.openverse.test",
        user_agent="glia-test",
        page_size=20,
        timeout_seconds=2,
        max_retries=1,
        client_id=client_id,
        client_secret=client_secret,
        transport=httpx.MockTransport(handler),
    )


def commons_lane(handler: Handler) -> CommonsLane:
    return CommonsLane(
        api_url="https://commons.test/w/api.php",
        user_agent="glia-test",
        page_size=20,
        timeout_seconds=2,
        max_retries=1,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_openverse_maps_the_documented_result_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/images/"
        assert request.url.params["license_type"] == "commercial"
        assert request.url.params["page_size"] == "20"
        assert request.url.params["q"] == "observatory"
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"results": [OPENVERSE_RESULT]})

    candidates = await openverse_lane(handler).search("observatory")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.id == "openverse:abc-123"
    assert candidate.lane == "open"
    assert candidate.image_url == OPENVERSE_RESULT["url"]
    assert candidate.source_url == OPENVERSE_RESULT["foreign_landing_url"]
    assert candidate.publisher == "flickr"
    assert candidate.licence == "BY-SA 2.0"
    assert (candidate.width, candidate.height) == (1024, 768)


@pytest.mark.asyncio
async def test_openverse_runs_anonymously_when_the_token_call_fails() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token/"):
            return httpx.Response(401, json={"detail": "nope"})
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"results": [OPENVERSE_RESULT]})

    lane = openverse_lane(handler, client_id="id", client_secret="secret")

    assert len(await lane.search("observatory")) == 1


@pytest.mark.asyncio
async def test_openverse_uses_the_token_when_one_is_issued() -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token/"):
            return httpx.Response(200, json={"access_token": "t0ken", "expires_in": 3600})
        seen.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json={"results": [OPENVERSE_RESULT]})

    lane = openverse_lane(handler, client_id="id", client_secret="secret")
    await lane.search("observatory")
    await lane.search("observatory")

    assert seen == ["Bearer t0ken", "Bearer t0ken"]


@pytest.mark.asyncio
async def test_openverse_drops_a_result_without_dimensions() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        undimensioned = {**OPENVERSE_RESULT, "id": "no-dims", "width": None, "height": None}
        return httpx.Response(200, json={"results": [OPENVERSE_RESULT, undimensioned]})

    candidates = await openverse_lane(handler).search("observatory")

    assert [candidate.id for candidate in candidates] == ["openverse:abc-123"]


@pytest.mark.asyncio
async def test_commons_maps_thumbnail_url_size_and_licence() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        assert params["generator"] == "search"
        assert params["gsrnamespace"] == "6"
        assert params["gsrsearch"] == "observatory filetype:bitmap"
        assert params["iiprop"] == "url|size|extmetadata"
        assert params["iiurlwidth"] == "800"
        assert request.headers["User-Agent"] == "glia-test"
        return httpx.Response(200, json={"query": {"pages": {"182355926": COMMONS_PAGE}}})

    candidates = await commons_lane(handler).search("observatory")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.id == "commons:182355926"
    assert candidate.publisher == "Wikimedia Commons"
    assert candidate.title == "Assy-Turgen Observatory"
    assert candidate.licence == "CC BY-SA 4.0"
    assert (candidate.width, candidate.height) == (800, 910)


@pytest.mark.asyncio
async def test_commons_returns_nothing_when_the_search_matched_nothing() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"batchcomplete": ""})

    assert await commons_lane(handler).search("observatory") == []


@pytest.mark.asyncio
async def test_a_lane_retries_a_transient_failure_but_never_a_4xx() -> None:
    attempts = {"transient": 0, "client_error": 0}

    async def transient(request: httpx.Request) -> httpx.Response:
        attempts["transient"] += 1
        if attempts["transient"] == 1:
            return httpx.Response(503, json={})
        return httpx.Response(200, json={"results": [OPENVERSE_RESULT]})

    async def client_error(request: httpx.Request) -> httpx.Response:
        attempts["client_error"] += 1
        return httpx.Response(400, json={})

    assert len(await openverse_lane(transient).search("observatory")) == 1
    assert attempts["transient"] == 2

    with pytest.raises(LaneUnavailable):
        await openverse_lane(client_error).search("observatory")
    assert attempts["client_error"] == 1


@pytest.mark.asyncio
async def test_a_lane_reports_unavailable_on_a_non_json_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>maintenance</html>")

    with pytest.raises(LaneUnavailable):
        await commons_lane(handler).search("observatory")


@pytest.mark.asyncio
async def test_a_lane_reports_unavailable_on_an_unexpected_shape() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"results": "not-a-list"}))

    with pytest.raises(LaneUnavailable):
        await openverse_lane(handler).search("observatory")
