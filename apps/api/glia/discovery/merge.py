"""Filtering, dedupe and lane interleaving for a discovery wave."""

import re
from collections.abc import Iterable, Sequence
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from glia.contracts import Candidate
from glia.discovery.fetch import host_allowed

_PUNCTUATION = re.compile(r"[^a-z0-9]+")
_TRACKING_PREFIXES = ("utm_",)
_NON_PHOTO_FILE = re.compile(r"\.(?:djvu?|eps|pdf|ps|svg)(?:[./_-]|$)", re.IGNORECASE)
_LOW_SIGNAL_TITLE_PATTERNS = (
    re.compile(
        r"\b(?:alphabet chart|character set|font specimen|glyph sheet|typeface|typography)\b"
    ),
    re.compile(
        r"\b(?:clip ?art|icon set|logo sheet|pictogram|vector graphic|vector illustration)\b"
    ),
    re.compile(
        r"\b(?:blueprint|diagram|flowchart|floor plan|organigram|schematic|technical drawing)\b"
    ),
    re.compile(
        r"\b(?:application form|book page|document scan|manuscript page|official form|"
        r"scan of|scanned document|title page)\b"
    ),
)


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
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, "")).rstrip(
        "/"
    )


def _is_low_signal_open_candidate(candidate: Candidate) -> bool:
    """Reject high-confidence document assets before they can dominate a wave.

    Commons renders PDF, DjVu and SVG pages as ordinary PNG/JPEG thumbnails. Those
    files satisfy the image contract but are generally scans, diagrams or vector
    specimens rather than useful reference photography. The title checks remain
    deliberately narrow: paintings and illustrations are still valid references,
    and ambiguous product photography should be kept.
    """
    paths = " ".join(
        unquote(urlsplit(url).path).casefold()
        for url in (candidate.image_url, candidate.source_url)
    )
    if _NON_PHOTO_FILE.search(paths):
        return True

    title = _PUNCTUATION.sub(" ", (candidate.title or "").casefold()).strip()
    return any(pattern.search(title) for pattern in _LOW_SIGNAL_TITLE_PATTERNS)


def is_servable(candidate: Candidate, *, min_edge: int, allowlist: tuple[str, ...]) -> bool:
    """Keep only candidates the grid can actually render.

    Reserved aspect boxes need real dimensions — a tile that reflows on load is
    the failure the whole layout is designed to avoid — so a candidate without
    them is dropped rather than guessed at. Perceptual-hash dedupe of visually
    identical crops is deliberately deferred; URL and title dedupe carry today.
    """
    if candidate.lane == "cited":
        # Cala's article pages are fetched and redirect-validated server-side before a candidate
        # reaches here. Their lead images remain origin URLs so attribution and publisher context
        # stay intact; the fixed sticker frame does not need guessed remote dimensions.
        return all(
            urlsplit(url).scheme.lower() == "https"
            for url in (candidate.image_url, candidate.source_url)
        )
    if candidate.width is None or candidate.height is None:
        return False
    if _is_low_signal_open_candidate(candidate):
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
    """Proxy allowlisted open-corpus images; keep Cala-cited images at their origin."""
    base = proxy_base.rstrip("/")
    return [
        (
            candidate
            if candidate.lane == "cited"
            else candidate.model_copy(
                update={"image_url": f"{base}/api/image?url={quote(candidate.image_url, safe='')}"}
            )
        )
        for candidate in candidates
    ]
