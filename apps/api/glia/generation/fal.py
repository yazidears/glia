"""Step (b) of Generate: the fal queue, over plain httpx.

Three constraints from docs/PARTNERS.md § 4 shape everything here.

1. Auth is ``Authorization: Key``, **not** ``Bearer``. A 401 is almost always this.
2. ``X-Fal-Store-IO: 0`` on every call. Our prompts contain summarised user speech and there is
   no reason for fal to keep it for thirty days.
3. The throttle is concurrency, and a new account gets two. One generation per session is in
   flight at a time and the second is refused, not queued.

Submit is **never retried**. A duplicate submit is a second billed generation for one click,
and a 202 we failed to read is still a generation running upstream.

Webhooks are deliberately absent. ``?fal_webhook=`` needs a publicly reachable callback and we
are on localhost, so it cannot work today; the queue is polled instead, on a hard cap.
"""

from __future__ import annotations

import asyncio
import ipaddress
import time
from typing import Any, Final
from urllib.parse import urlparse

import httpx
import structlog

from glia.config import Settings

logger = structlog.get_logger(__name__)

_TERMINAL_FAILURES: Final = frozenset({"ERROR", "FAILED", "CANCELLED"})


class FalNotConfigured(Exception):
    """No FAL_KEY. The route says so rather than pretending to have generated."""


class FalTimedOut(Exception):
    """The poll cap elapsed. The generation may still complete upstream, and is still billed."""


class FalReferenceUnavailable(Exception):
    """fal could not fetch one of the reference images it was handed.

    Verified live on 29 Aug 2026: the queue reports such a request as ``COMPLETED``, and the
    rejection only appears as a 422 from the *result* endpoint with
    ``detail[].type == "file_download_error"``. So this is not a transport failure and retrying
    it never helps — the URL is one fal cannot reach.

    Since ``generation/references.py`` re-hosts every reference on fal's own storage before
    submitting, this should now be unreachable in practice. It is kept, and kept typed, because
    the alternative to a wrong claim about the future is a path that still tells the truth: it
    is the one generation failure the user can act on, and collapsing it into "temporarily
    unavailable" would be both wrong and unhelpful.
    """


class FalUpstreamError(Exception):
    """Anything else. The vendor body never leaves this module."""


def is_public_https(url: str | None) -> bool:
    """Whether this URL is one the server may fetch on fal's behalf.

    Anything that is not public https is not a reference: no data: URIs, no blob:, no
    localhost, no private ranges — which is exactly what rules out our own `/api/image` proxy.
    A URL that fails this is not passed off as a reference and not silently repaired; the pin
    still steers the prompt through its title, and `reference_count` reports the truth.
    """
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith((".local", ".localhost")):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (address.is_private or address.is_loopback or address.is_link_local)


class FalClient:
    """Owns the key, the timeouts, the poll cap and the one-in-flight rule."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._queue_base = settings.fal_queue_base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            connect=settings.fal_connect_timeout_seconds,
            read=settings.fal_request_timeout_seconds,
            write=settings.fal_connect_timeout_seconds,
            pool=settings.fal_connect_timeout_seconds,
        )
        self._in_flight: set[str] = set()

    @property
    def configured(self) -> bool:
        return self._settings.fal_key is not None

    def acquire(self, session_id: str) -> bool:
        """Claim this session's single generation slot. False means one is already running.

        A plain set is enough: the event loop never interleaves between this check and the add,
        so two clicks in the same tick cannot both win.
        """
        if session_id in self._in_flight:
            return False
        self._in_flight.add(session_id)
        return True

    def release(self, session_id: str) -> None:
        self._in_flight.discard(session_id)

    def model_for(self, reference_count: int) -> str:
        """References or no references — that is the whole model choice."""
        if reference_count:
            return self._settings.fal_reference_model
        return self._settings.fal_fallback_model

    async def generate(self, *, model: str, prompt: str, references: list[str]) -> str:
        """Submit, poll, and return the image URL. One submit, no retries."""
        key = self._settings.fal_key
        if key is None:
            raise FalNotConfigured("FAL_KEY is not set.")
        headers = {
            # Key, not Bearer. See docs/PARTNERS.md § 4.
            "Authorization": f"Key {key.get_secret_value()}",
            "Accept": "application/json",
            # Suppresses fal's 30-day payload retention. Our prompts are summarised speech.
            "X-Fal-Store-IO": "0",
        }
        arguments: dict[str, Any] = {"prompt": prompt}
        if references:
            arguments["image_urls"] = references

        deadline = time.monotonic() + self._settings.fal_poll_timeout_seconds
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            submitted = await self._submit(client, model, arguments, headers)
            status_url = self._queue_url(submitted, "status_url")
            response_url = self._queue_url(submitted, "response_url")
            logger.info(
                "fal.submitted",
                model=model,
                reference_count=len(references),
                request_id=submitted.get("request_id"),
            )
            await self._await_completion(client, status_url, headers, deadline)
            payload = await self._get(client, response_url, headers, endpoint="result")

        image_url = _first_image_url(payload)
        if image_url is None:
            raise FalUpstreamError("fal returned a result with no image.")
        return image_url

    async def _submit(
        self,
        client: httpx.AsyncClient,
        model: str,
        arguments: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        url = f"{self._queue_base}/{model.strip('/')}"
        try:
            response = await client.post(url, json=arguments, headers=headers)
        except httpx.HTTPError as error:
            # Not retried even when it provably never landed: a submit we cannot account for is
            # cheaper to fail than to risk billing twice for one click.
            raise FalUpstreamError("fal did not accept the request.") from error
        payload = self._json(response, endpoint="submit")
        if not isinstance(payload, dict):
            raise FalUpstreamError("fal returned a non-object submit response.")
        return payload

    async def _await_completion(
        self,
        client: httpx.AsyncClient,
        status_url: str,
        headers: dict[str, str],
        deadline: float,
    ) -> None:
        interval = self._settings.fal_poll_interval_seconds
        while True:
            payload = await self._get(client, status_url, headers, endpoint="status")
            status = payload.get("status")
            if status == "COMPLETED":
                return
            if isinstance(status, str) and status.upper() in _TERMINAL_FAILURES:
                logger.warning("fal.request.failed", status=status)
                raise FalUpstreamError(f"fal reported {status}.")
            if time.monotonic() + interval >= deadline:
                logger.warning("fal.poll.timed_out", last_status=status)
                raise FalTimedOut("fal did not finish inside the poll window.")
            await asyncio.sleep(interval)

    async def _get(
        self, client: httpx.AsyncClient, url: str, headers: dict[str, str], *, endpoint: str
    ) -> dict[str, Any]:
        try:
            response = await client.get(url, headers=headers)
        except httpx.HTTPError as error:
            raise FalUpstreamError("fal did not answer.") from error
        payload = self._json(response, endpoint=endpoint)
        if not isinstance(payload, dict):
            raise FalUpstreamError("fal returned a non-object response.")
        return payload

    def _json(self, response: httpx.Response, *, endpoint: str) -> Any:
        if response.status_code == 422 and _is_reference_download_failure(response):
            logger.warning("fal.reference.unfetchable", endpoint=endpoint)
            raise FalReferenceUnavailable("fal could not fetch a reference image.")
        if response.status_code >= 400:
            # Logged by status, never returned: it is a vendor body and may carry account
            # detail that has no business in an HTTP reply of ours.
            logger.warning("fal.request.rejected", status=response.status_code, endpoint=endpoint)
            raise FalUpstreamError(f"fal returned {response.status_code}.")
        try:
            return response.json()
        except ValueError as error:
            raise FalUpstreamError("fal returned a body that is not JSON.") from error

    def _queue_url(self, submitted: dict[str, Any], field: str) -> str:
        """Follow fal's own `status_url` / `response_url` rather than building them.

        The queue paths for a nested model id (`fal-ai/flux-pro/kontext/max/multi`) are not the
        model id — they truncate to the app. Trusting the submit response removes that trap,
        and pinning the host is what keeps a trusted response from becoming an open fetch.
        """
        value = submitted.get(field)
        if not isinstance(value, str) or not value:
            raise FalUpstreamError(f"fal did not return a {field}.")
        parsed = urlparse(value)
        expected = urlparse(self._queue_base)
        if parsed.scheme != "https" or parsed.hostname != expected.hostname:
            raise FalUpstreamError(f"fal returned an unexpected {field}.")
        return value


def _is_reference_download_failure(response: httpx.Response) -> bool:
    """Classify a 422 without repeating any of it back to the client.

    Only the machine-readable `type` is read. The vendor's message may name URLs and account
    detail and never leaves this module.
    """
    try:
        body = response.json()
    except ValueError:
        return False
    if not isinstance(body, dict):
        return False
    detail = body.get("detail")
    if not isinstance(detail, list):
        return False
    return any(
        isinstance(item, dict) and item.get("type") == "file_download_error" for item in detail
    )


def _first_image_url(payload: dict[str, Any]) -> str | None:
    """Model families differ: flux returns `images[]`, some edit models return `image`."""
    images = payload.get("images")
    if isinstance(images, list):
        for item in images:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                return str(item["url"])
    single = payload.get("image")
    if isinstance(single, dict) and isinstance(single.get("url"), str):
        return str(single["url"])
    return None
