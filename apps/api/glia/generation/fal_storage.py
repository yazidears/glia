"""fal's object storage, over plain httpx — the hop that makes a pinned reference reachable.

Handing fal an origin URL does not work, for two independent reasons measured on 29 Aug 2026.

1. A grid tile's `image_url` is our own `/api/image` proxy on localhost. fal fetches references
   from its own infrastructure and cannot reach this machine at all.
2. Even the origin URL often fails. fal's fetcher sends a blank User-Agent and
   `upload.wikimedia.org` answers that with 403 — and Commons is a primary Lane B source, so
   that is the common case rather than an edge one.

So the bytes travel through us: fetched under the guards in `discovery/fetch.py`, then uploaded
here, and it is a URL on fal's own storage that the model is given.

Two calls, both using the same `Authorization: Key` as the queue (see docs/PARTNERS.md § 4 —
Key, never Bearer):

    POST {rest}/storage/upload/initiate?storage_type=fal-cdn-v3  → {upload_url, file_url}
    PUT  {upload_url}                                            ← the bytes

The storage type is sent explicitly rather than left to the server default, and it is also the
only value that works: measured against the live API on 29 Aug 2026, `storage_type=gcs` — which
`fal_client` sends on its fallback path — is answered with `400 {"detail": "Invalid storage
type"}`. The value here is the measured one, not the documented one.

`upload_url` is a signed URL whose host fal chooses, so unlike the queue's `status_url` it
cannot be pinned to a known host. It gets the next best thing: https only, and the same
resolved-address check the image fetcher applies, so a hostname pointing at a private range or
at cloud metadata is refused before we connect. That nothing is read back from the response is
*not* the argument — a blind write to an internal endpoint is a real thing, and the guard here
does not depend on the direction of the data.
"""

from __future__ import annotations

import mimetypes
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from glia.config import Settings
from glia.discovery.fetch import resolves_publicly

logger = structlog.get_logger(__name__)

#: fal names the object by this; nothing from the origin URL goes into it. The extension is the
#: only part that carries information, and it comes from the content-type our own fetcher
#: verified rather than from anything the remote host chose to call the file.
_UPLOAD_STEM = "reference"
_DEFAULT_EXTENSION = ".jpg"

#: fal's current CDN. Measured, not assumed — see the module docstring.
_STORAGE_TYPE = "fal-cdn-v3"


class FalStorageError(RuntimeError):
    """The reference could not be re-hosted. The vendor body never leaves this module."""


class FalStorage:
    """Uploads reference bytes to fal and returns the URL a model can read."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.fal_rest_base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            connect=settings.fal_connect_timeout_seconds,
            read=settings.fal_upload_timeout_seconds,
            write=settings.fal_upload_timeout_seconds,
            pool=settings.fal_connect_timeout_seconds,
        )

    @property
    def configured(self) -> bool:
        return self._settings.fal_key is not None

    async def upload(self, data: bytes, *, content_type: str) -> str:
        key = self._settings.fal_key
        if key is None:
            raise FalStorageError("FAL_KEY is not set.")
        headers = {
            # Key, not Bearer. Same as the queue.
            "Authorization": f"Key {key.get_secret_value()}",
            "Accept": "application/json",
            # Our own bytes are not the concern here, but the header is set on every fal call
            # so that "every fal call" stays a rule with no exceptions to remember.
            "X-Fal-Store-IO": "0",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            initiated = await self._initiate(client, content_type, headers)
            upload_url = _https_url(initiated, "upload_url")
            file_url = _https_url(initiated, "file_url")
            await self._put(client, upload_url, data, content_type)
        return file_url

    async def _initiate(
        self, client: httpx.AsyncClient, content_type: str, headers: dict[str, str]
    ) -> dict[str, Any]:
        url = f"{self._base}/storage/upload/initiate?storage_type={_STORAGE_TYPE}"
        try:
            response = await client.post(
                url,
                json={"file_name": _file_name(content_type), "content_type": content_type},
                headers={**headers, "Content-Type": "application/json"},
            )
        except httpx.HTTPError as error:
            raise FalStorageError("fal storage did not answer.") from error
        if response.status_code >= 400:
            # Logged by status, never returned: a vendor body may carry account detail.
            logger.warning("fal.storage.rejected", status=response.status_code, step="initiate")
            raise FalStorageError(f"fal storage returned {response.status_code}.")
        try:
            payload = response.json()
        except ValueError as error:
            raise FalStorageError("fal storage returned a body that is not JSON.") from error
        if not isinstance(payload, dict):
            raise FalStorageError("fal storage returned a non-object response.")
        return payload

    async def _put(
        self, client: httpx.AsyncClient, upload_url: str, data: bytes, content_type: str
    ) -> None:
        try:
            response = await client.put(
                upload_url, content=data, headers={"Content-Type": content_type}
            )
        except httpx.HTTPError as error:
            raise FalStorageError("fal storage did not accept the upload.") from error
        if response.status_code >= 400:
            logger.warning("fal.storage.rejected", status=response.status_code, step="put")
            raise FalStorageError(f"fal storage returned {response.status_code}.")


def _file_name(content_type: str) -> str:
    extension = mimetypes.guess_extension(content_type) or _DEFAULT_EXTENSION
    return f"{_UPLOAD_STEM}{extension}"


def _https_url(payload: dict[str, Any], field: str) -> str:
    """A URL from fal's own authenticated reply, still checked before we use it.

    The trust boundary is fal's API, which is a good one — but "the response came from a
    service we authenticated to" is a reason to be surprised by a private address here, not a
    reason to be unable to notice one.
    """
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise FalStorageError(f"fal storage did not return a {field}.")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise FalStorageError(f"fal storage returned an unusable {field}.")
    if not resolves_publicly(parsed.hostname):
        logger.warning("fal.storage.non_public_url", field=field)
        raise FalStorageError(f"fal storage returned a non-public {field}.")
    return value
