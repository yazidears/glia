"""Wikimedia Commons image lane.

No auth, but Wikimedia blocks generic User-Agents outright, so the configured
contact UA is mandatory rather than polite.
"""

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from glia.contracts import Candidate
from glia.discovery.lane import LaneUnavailable, get_json, rank_score

FILE_NAMESPACE = 6


class _ExtMetadataValue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: str | None = None


class _ExtMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    LicenseShortName: _ExtMetadataValue | None = None
    ObjectName: _ExtMetadataValue | None = None


class _ImageInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    thumburl: str | None = None
    descriptionurl: str | None = None
    thumbwidth: int | None = None
    thumbheight: int | None = None
    extmetadata: _ExtMetadata | None = None


class _Page(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pageid: int
    index: int = 0
    title: str = ""
    imageinfo: list[_ImageInfo] = []


class _Query(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pages: dict[str, _Page] = {}


class _CommonsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: _Query | None = None


class CommonsLane:
    def __init__(
        self,
        *,
        api_url: str,
        user_agent: str,
        page_size: int,
        timeout_seconds: float,
        max_retries: int,
        thumb_width: int = 800,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_url = api_url
        self._user_agent = user_agent
        self._page_size = page_size
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_retries = max_retries
        self._thumb_width = thumb_width
        self._transport = transport

    @property
    def name(self) -> str:
        return "commons"

    async def search(self, query: str) -> list[Candidate]:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            body = await get_json(
                client=client,
                url=self._api_url,
                params={
                    "action": "query",
                    "format": "json",
                    "formatversion": "1",
                    "generator": "search",
                    "gsrnamespace": FILE_NAMESPACE,
                    "gsrsearch": query,
                    "gsrlimit": self._page_size,
                    "prop": "imageinfo",
                    "iiprop": "url|size|extmetadata",
                    "iiurlwidth": self._thumb_width,
                },
                headers={"User-Agent": self._user_agent, "Accept": "application/json"},
                max_retries=self._max_retries,
            )
        try:
            parsed = _CommonsResponse.model_validate(body)
        except ValidationError as error:
            raise LaneUnavailable("Commons returned an unsupported result shape") from error
        if parsed.query is None:
            return []
        pages = sorted(parsed.query.pages.values(), key=lambda page: page.index)
        return [
            candidate
            for position, page in enumerate(pages)
            if (candidate := self._to_candidate(position, len(pages), page)) is not None
        ]

    def _to_candidate(self, index: int, total: int, page: _Page) -> Candidate | None:
        if not page.imageinfo:
            return None
        info = page.imageinfo[0]
        if not info.thumburl or not info.descriptionurl:
            return None
        if info.thumbwidth is None or info.thumbheight is None:
            return None
        return Candidate(
            id=f"commons:{page.pageid}",
            lane="open",
            image_url=info.thumburl,
            source_url=info.descriptionurl,
            publisher="Wikimedia Commons",
            title=_title(page, info),
            licence=_licence(info),
            width=info.thumbwidth,
            height=info.thumbheight,
            score=rank_score(index, total, info.thumbwidth, info.thumbheight),
        )


def _licence(info: _ImageInfo) -> str | None:
    if info.extmetadata is None or info.extmetadata.LicenseShortName is None:
        return None
    value = info.extmetadata.LicenseShortName.value
    return value.strip() if value and value.strip() else None


def _title(page: _Page, info: _ImageInfo) -> str | None:
    if info.extmetadata is not None and info.extmetadata.ObjectName is not None:
        described = (info.extmetadata.ObjectName.value or "").strip()
        # Commons descriptions may carry wiki or HTML markup; fall back to the
        # file name rather than shipping markup the UI would have to strip.
        if described and "<" not in described:
            return described
    title = page.title.removeprefix("File:").rsplit(".", maxsplit=1)[0]
    title = title.replace("_", " ").strip()
    return title or None
