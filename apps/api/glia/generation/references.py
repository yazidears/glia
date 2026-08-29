"""Pinned references, turned into something fal can actually fetch.

The rule this module exists to keep: **nothing derived from `PinnedRef.image_url` is ever sent
to fal.** That field is the display URL and for a grid tile it is our own `/api/image` proxy on
localhost, which fal cannot reach. Generation reads `origin_image_url`, fetches it here under
the guards in `discovery/fetch.py`, re-hosts the bytes on fal's storage, and passes the fal URL.

One bad pin is not a failed generation. Each reference is fetched and uploaded on its own
budget, and a pin that fails is dropped by id — the generation runs on the pins that worked, the
prompt still carries every pin's title, and `reference_count` reports what actually conditioned
the image rather than what was hoped for.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

import structlog

from glia.contracts import PinnedRef
from glia.discovery.fetch import FetchFailed, FetchRejected, ImageBytes
from glia.generation.fal import is_public_https
from glia.generation.fal_storage import FalStorageError

logger = structlog.get_logger(__name__)


class ImageSource(Protocol):
    """The read half of `discovery.fetch.ImageFetcher`, named so the resolver depends on the
    capability rather than the class. In production it is always that fetcher — there is one,
    and it owns the guards."""

    async def read(self, raw_url: str) -> ImageBytes: ...


class ReferenceStore(Protocol):
    """The upload half of `generation.fal_storage.FalStorage`."""

    async def upload(self, data: bytes, *, content_type: str) -> str: ...


def reference_pins(pins: list[PinnedRef], limit: int) -> list[PinnedRef]:
    """The pins that could become references, capped at FAL_MAX_REFERENCE_IMAGES.

    Eligibility is about `origin_image_url` alone. A sticker has none and is not a reference; a
    grid tile has one and is a candidate for the round trip below. `image_url` is not consulted,
    which is what makes "the proxy URL never reaches fal" a property of the code rather than a
    thing to remember.
    """
    return [pin for pin in pins if is_public_https(pin.origin_image_url)][:limit]


@dataclass(frozen=True)
class ResolvedReferences:
    """What generation may condition on, and which pins did not make it.

    `delivered` and `unavailable` partition the eligible pins, so a caller never has to
    reconstruct "which pins did we actually send" from the eligibility rule a second time —
    doing that is how a pin that uploaded fine ends up reported as broken.
    """

    #: fal-hosted URLs, in pin order.
    urls: list[str]
    #: Ids of the pins those URLs came from, positionally aligned with `urls`.
    delivered: list[str]
    #: Ids of eligible pins we could not deliver. The user's list to act on.
    unavailable: list[str]


class ReferenceResolver:
    def __init__(
        self,
        *,
        fetcher: ImageSource,
        storage: ReferenceStore,
        max_references: int,
        timeout: float,
    ) -> None:
        self._fetcher = fetcher
        self._storage = storage
        self._max_references = max_references
        self._timeout = timeout

    async def resolve(self, pins: list[PinnedRef]) -> ResolvedReferences:
        """Fetch and re-host every eligible pin, concurrently, and report the casualties.

        The timeout is per reference rather than over the batch: a single slow origin host
        should cost that one pin, not the three that were already on their way.
        """
        eligible = reference_pins(pins, self._max_references)
        if not eligible:
            return ResolvedReferences(urls=[], delivered=[], unavailable=[])

        hosted = await asyncio.gather(*(self._rehost(pin) for pin in eligible))
        pairs = list(zip(eligible, hosted, strict=True))
        urls = [url for _, url in pairs if url is not None]
        delivered = [pin.id for pin, url in pairs if url is not None]
        unavailable = [pin.id for pin, url in pairs if url is None]
        if unavailable:
            logger.warning(
                "generate.reference.dropped", dropped=len(unavailable), kept=len(urls)
            )
        return ResolvedReferences(urls=urls, delivered=delivered, unavailable=unavailable)

    async def _rehost(self, pin: PinnedRef) -> str | None:
        """One pin's round trip. Returns None for every way it can fail, and never raises.

        Broad by design at the bottom: this runs inside `asyncio.gather` for a generation the
        user is waiting on, and an unanticipated error from a remote host must cost one
        reference, not the whole image.
        """
        origin = pin.origin_image_url
        if origin is None:
            return None
        try:
            async with asyncio.timeout(self._timeout):
                image = await self._fetcher.read(origin)
                return await self._storage.upload(image.data, content_type=image.content_type)
        except (FetchRejected, FetchFailed, FalStorageError, TimeoutError) as error:
            logger.warning(
                "generate.reference.unfetchable", pin=pin.id, error=type(error).__name__
            )
            return None
        except Exception as error:  # one pin must never take the generation down with it
            logger.warning("generate.reference.crashed", pin=pin.id, error=type(error).__name__)
            return None
