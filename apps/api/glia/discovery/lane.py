"""Shared plumbing for the open-corpus image lanes.

Both lanes talk to hardcoded API hosts, so these requests do not go through
``glia.discovery.fetch`` — that fetcher exists for URLs the open web chose for
us, which here means the image URLs these responses contain.
"""

import asyncio
from typing import Protocol, cast

import httpx

from glia.contracts import Candidate

TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
RETRY_BACKOFF_SECONDS = 0.15


class LaneUnavailable(RuntimeError):
    """A lane could not answer. The other lane carries the wave."""


class ImageLane(Protocol):
    @property
    def name(self) -> str: ...

    async def search(self, query: str) -> list[Candidate]: ...


async def get_json(
    *,
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, str | int],
    headers: dict[str, str],
    max_retries: int,
) -> dict[str, object]:
    """GET a JSON object, retrying transient failures only — never a 4xx."""
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code in TRANSIENT_STATUSES and attempt < max_retries:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            response.raise_for_status()
            parsed = response.json()
        except httpx.HTTPStatusError as error:
            last_error = error
            if error.response.status_code in TRANSIENT_STATUSES and attempt < max_retries:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            break
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            last_error = error
            if attempt < max_retries:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            break
        except ValueError as error:
            raise LaneUnavailable("Upstream returned invalid JSON") from error
        if not isinstance(parsed, dict):
            raise LaneUnavailable("Upstream returned a non-object response")
        return cast(dict[str, object], parsed)
    raise LaneUnavailable("Upstream is temporarily unavailable") from last_error


def rank_score(index: int, total: int, width: int, height: int) -> float:
    """Rank position carries most of the weight; resolution breaks ties."""
    position = 1.0 - (index / max(total, 1)) * 0.4
    resolution = min(min(width, height) / 1_600, 1.0) * 0.1
    return round(min(position + resolution, 1.0), 4)
