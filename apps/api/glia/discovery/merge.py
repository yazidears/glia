"""Filtering, dedupe and lane interleaving for a discovery wave."""

import re
from collections.abc import Iterable, Sequence
from urllib.parse import quote, urlsplit, urlunsplit

from glia.contracts import Candidate
from glia.discovery.fetch import host_allowed

_PUNCTUATION = re.compile(r"[^a-z0-9]+")
_TRACKING_PREFIXES = ("utm_",)


def dedupe_key(candidate: Candidate) -> str:
    return f"url:{normalise_url(candidate.image_url)}"


def title_key(candidate: Candidate) -> str | None:
    if candidate.title is None:
        return None
    normalised = _PUNCTUATION.sub(" ", candidate.title.lower()).strip()
    return f"title:{normalised}" if normalised else None


def normalise_url(raw: str) -> str:
    """Lowercase the authority and drop tracking params, for dedupe only."""
    parts = urlsplit(raw)
    query = "&".join(
        param
        for param in parts.query.split("&")
        if param and not param.lower().startswith(_TRACKING_PREFIXES)
    )
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, query, "")
    ).rstrip("/")


def is_servable(candidate: Candidate, *, min_edge: int, allowlist: tuple[str, ...]) -> bool:
    """Keep only candidates the grid can actually render.

    Reserved aspect boxes need real dimensions — a tile that reflows on load is
    the failure the whole layout is designed to avoid — so a candidate without
    them is dropped rather than guessed at. Perceptual-hash dedupe of visually
    identical crops is deliberately deferred; URL and title dedupe carry today.
    """
    if candidate.width is None or candidate.height is None:
        return False
    if candidate.width < min_edge or candidate.height < min_edge:
        return False
    for url in (candidate.image_url, candidate.source_url):
        if urlsplit(url).scheme.lower() not in {"http", "https"}:
            return False
    host = urlsplit(candidate.image_url).hostname
    return host is not None and host_allowed(host, allowlist)


def interleave(lanes: Sequence[Sequence[Candidate]]) -> list[Candidate]:
    """Round-robin the lanes so a wave reads as mixed, not as two blocks."""
    merged: list[Candidate] = []
    for column in range(max((len(lane) for lane in lanes), default=0)):
        for lane in lanes:
            if column < len(lane):
                merged.append(lane[column])
    return merged


def select_new(
    lanes: Sequence[Sequence[Candidate]],
    *,
    seen: set[str],
    min_edge: int,
    allowlist: tuple[str, ...],
    limit: int,
) -> list[Candidate]:
    """Filter, dedupe against what already shipped, interleave and cap.

    Only the candidates that actually ship are marked seen: one trimmed by the
    cap has to stay eligible for the next wave.
    """
    within_call: set[str] = set()
    filtered: list[list[Candidate]] = []
    for lane in lanes:
        kept: list[Candidate] = []
        for candidate in lane:
            if not is_servable(candidate, min_edge=min_edge, allowlist=allowlist):
                continue
            keys = _keys(candidate)
            if any(key in seen or key in within_call for key in keys):
                continue
            within_call.update(keys)
            kept.append(candidate)
        filtered.append(kept)

    selected = interleave(filtered)[:limit]
    for candidate in selected:
        seen.update(_keys(candidate))
    return selected


def _keys(candidate: Candidate) -> list[str]:
    return [key for key in (dedupe_key(candidate), title_key(candidate)) if key]


def proxied(candidates: Iterable[Candidate], *, proxy_base: str) -> list[Candidate]:
    """Rewrite image_url through our own proxy, keeping the origin file on the candidate.

    This is the one place a candidate's image URL changes, so it is the one place that can
    truthfully record what it was. `origin_image_url` is set here rather than at each lane
    because "the URL before the rewrite" is a fact about the rewrite: a lane cannot get it
    wrong, and a candidate that never passes through here keeps its null.

    The origin is not `source_url` and never was — that is a landing page, and handing it to an
    image fetcher returns HTML. Generation needs the file, so the file is what is carried.
    """
    base = proxy_base.rstrip("/")
    return [
        candidate.model_copy(
            update={
                "image_url": f"{base}/api/image?url={quote(candidate.image_url, safe='')}",
                "origin_image_url": candidate.image_url,
            }
        )
        for candidate in candidates
    ]
