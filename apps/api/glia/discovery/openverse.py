"""Openverse image lane.

Anonymous access works at a lower rate limit, so a missing or rejected client
credential degrades to anonymous rather than taking the lane down.
"""

import time

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from glia.contracts import Candidate
from glia.discovery.lane import LaneUnavailable, get_json, rank_score

TOKEN_REFRESH_MARGIN_SECONDS = 30


class _OpenverseResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str | None = None
    url: str | None = None
    foreign_landing_url: str | None = None
    source: str | None = None
    license: str | None = None
    license_version: str | None = None
    width: int | None = None
    height: int | None = None


class _OpenverseResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[_OpenverseResult] = []


class OpenverseLane:
    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        page_size: int,
        timeout_seconds: float,
        max_retries: int,
        client_id: str | None = None,
        client_secret: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._page_size = page_size
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_retries = max_retries
        self._client_id = client_id
        self._client_secret = client_secret
        self._transport = transport
        self._token: str | None = None
        self._token_expires_at = 0.0

    @property
    def name(self) -> str:
        return "openverse"

    async def search(self, query: str) -> list[Candidate]:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            headers = {"User-Agent": self._user_agent, "Accept": "application/json"}
            token = await self._access_token(client)
            if token is not None:
                headers["Authorization"] = f"Bearer {token}"
            body = await get_json(
                client=client,
                url=f"{self._base_url}/v1/images/",
                params={
                    "q": query,
                    "page_size": self._page_size,
                    "license_type": "commercial",
                },
                headers=headers,
                max_retries=self._max_retries,
            )
        try:
            parsed = _OpenverseResponse.model_validate(body)
        except ValidationError as error:
            raise LaneUnavailable("Openverse returned an unsupported result shape") from error
        return [
            candidate
            for index, result in enumerate(parsed.results)
            if (candidate := self._to_candidate(index, len(parsed.results), result)) is not None
        ]

    async def _access_token(self, client: httpx.AsyncClient) -> str | None:
        """Return a bearer token, or None to run the lane anonymously."""
        if self._client_id is None or self._client_secret is None:
            return None
        if self._token is not None and time.monotonic() < self._token_expires_at:
            return self._token
        try:
            response = await client.post(
                f"{self._base_url}/v1/auth_tokens/token/",
                headers={"User-Agent": self._user_agent},
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not isinstance(token, str) or not token:
            return None
        lifetime = expires_in if isinstance(expires_in, int) else 0
        self._token = token
        self._token_expires_at = time.monotonic() + max(lifetime - TOKEN_REFRESH_MARGIN_SECONDS, 0)
        return token

    def _to_candidate(
        self, index: int, total: int, result: _OpenverseResult
    ) -> Candidate | None:
        if not result.url or not result.foreign_landing_url:
            return None
        if result.width is None or result.height is None:
            return None
        return Candidate(
            id=f"openverse:{result.id}",
            lane="open",
            image_url=result.url,
            source_url=result.foreign_landing_url,
            publisher=result.source,
            title=result.title,
            licence=_licence(result),
            width=result.width,
            height=result.height,
            score=rank_score(index, total, result.width, result.height),
        )


def _licence(result: _OpenverseResult) -> str | None:
    parts = [part for part in (result.license, result.license_version) if part]
    return " ".join(parts).upper() if parts else None
