"""The one fetcher for URLs Glia did not hardcode.

Every image discovered by a lane is served through here. Nothing else in the
app may request a remote-supplied URL. See docs/SECURITY.md, "The image
fetcher" — this module owns the scheme allowlist, the host allowlist, the
resolved-address check, redirect refusal, the content-type check and the byte
cap enforced while streaming.
"""

import ipaddress
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

ALLOWED_SCHEMES = frozenset({"https"})
ALLOWED_PORTS = frozenset({443})
MAX_URL_LENGTH = 2_000


class FetchRejected(ValueError):
    """The URL failed a guard. Never surface the reason to the client verbatim."""


class FetchFailed(RuntimeError):
    """The upstream host did not return a usable image."""


@dataclass(frozen=True)
class ImageStream:
    content_type: str
    chunks: AsyncIterator[bytes]


@dataclass(frozen=True)
class ImageBytes:
    """A whole image in memory, for the one caller that cannot relay a stream."""

    content_type: str
    data: bytes


def host_allowed(host: str, allowlist: tuple[str, ...]) -> bool:
    """Suffix match on label boundaries, so `evil-wikimedia.org` never matches."""
    normalised = host.lower().rstrip(".")
    return any(
        normalised == suffix.lower() or normalised.endswith(f".{suffix.lower()}")
        for suffix in allowlist
    )


def validate_image_url(raw: str, allowlist: tuple[str, ...]) -> str:
    """Return the URL only if every guard passes; raise FetchRejected otherwise."""
    if not raw or len(raw) > MAX_URL_LENGTH:
        raise FetchRejected("URL is missing or too long")
    parts = urlsplit(raw)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise FetchRejected("Only https URLs are fetched")
    if parts.username or parts.password:
        raise FetchRejected("Credentials in URLs are refused")
    host = parts.hostname
    if host is None:
        raise FetchRejected("URL has no host")
    try:
        port = parts.port
    except ValueError as error:
        raise FetchRejected("URL has an invalid port") from error
    if port is not None and port not in ALLOWED_PORTS:
        raise FetchRejected("Only the default https port is fetched")
    if not host_allowed(host, allowlist):
        raise FetchRejected("Host is not an allowed image host")
    _reject_private_addresses(host)
    return raw


def resolves_publicly(host: str) -> bool:
    """Whether every address this host resolves to is a public one.

    The address rules live here and only here. Any outbound request built from a URL we did not
    hardcode goes through this, so that there is one definition of "not public" to keep correct
    rather than one per call site.
    """
    try:
        resolved = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    if not resolved:
        return False
    for entry in resolved:
        address = ipaddress.ip_address(str(entry[4][0]))
        if address.is_private or address.is_loopback or address.is_link_local:
            return False
        if address.is_reserved or address.is_multicast or address.is_unspecified:
            return False
    return True


def _reject_private_addresses(host: str) -> None:
    """Resolve before connecting and refuse anything that is not public.

    Aikido's taint analysis will flag the request below as SSRF because the URL
    began life in a remote response. This function, plus the host allowlist and
    the refusal to follow redirects, is the control that answers that finding.
    """
    if not resolves_publicly(host):
        raise FetchRejected("Host does not resolve to a public address")


class ImageFetcher:
    def __init__(
        self,
        *,
        allowlist: tuple[str, ...],
        user_agent: str,
        max_bytes: int,
        connect_timeout: float,
        total_timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._allowlist = allowlist
        self._user_agent = user_agent
        self._max_bytes = max_bytes
        self._timeout = httpx.Timeout(total_timeout, connect=connect_timeout)
        self._transport = transport

    async def open(self, raw_url: str) -> ImageStream:
        url = validate_image_url(raw_url, self._allowlist)
        client = httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
            follow_redirects=False,
        )
        request = client.build_request(
            "GET",
            url,
            headers={"User-Agent": self._user_agent, "Accept": "image/*"},
        )
        try:
            response = await client.send(request, stream=True)
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            await client.aclose()
            raise FetchFailed("Upstream image host did not respond") from error

        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        declared = response.headers.get("content-length")
        try:
            if response.is_redirect:
                # A redirect would need full re-validation of the new hop; the
                # allowlisted hosts never need one, so refuse instead.
                raise FetchFailed("Upstream image host redirected")
            if response.status_code != httpx.codes.OK:
                raise FetchFailed("Upstream image host returned an error")
            if not content_type.startswith("image/"):
                raise FetchFailed("Upstream response is not an image")
            if declared is not None and declared.isdigit() and int(declared) > self._max_bytes:
                raise FetchFailed("Upstream image exceeds the size cap")
        except FetchFailed:
            await response.aclose()
            await client.aclose()
            raise

        return ImageStream(
            content_type=content_type,
            chunks=self._stream(client, response),
        )

    async def read(self, raw_url: str) -> ImageBytes:
        """The same guards as `open`, buffered — for uploading rather than relaying.

        The proxy can hand a browser a stream. A reference image cannot be streamed anywhere:
        fal wants the bytes, so they are collected here, still through the one fetcher that
        owns the allowlist, the resolved-address check, the redirect refusal and the cap.

        `open` stops yielding at the cap rather than raising, so a body that reaches it is
        either exactly the cap or was truncated at it. A truncated image is not a reference
        worth conditioning on, and the two are indistinguishable, so both are refused.
        """
        stream = await self.open(raw_url)
        buffer = bytearray()
        async for chunk in stream.chunks:
            buffer += chunk
        if len(buffer) >= self._max_bytes:
            raise FetchFailed("Upstream image exceeds the size cap")
        if not buffer:
            raise FetchFailed("Upstream image host returned an empty body")
        return ImageBytes(content_type=stream.content_type, data=bytes(buffer))

    async def _stream(
        self, client: httpx.AsyncClient, response: httpx.Response
    ) -> AsyncIterator[bytes]:
        # Content-Length is attacker-controlled and may be absent, so the cap is
        # enforced against bytes actually read.
        seen = 0
        try:
            async for chunk in response.aiter_bytes():
                seen += len(chunk)
                if seen > self._max_bytes:
                    break
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()
