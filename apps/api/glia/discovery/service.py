"""Lane B discovery: run the open corpora concurrently and stream waves out.

The lanes are independent by construction — one lane failing degrades the wave
to the other lane rather than emptying the grid — and results are emitted in
small waves as they land, because a grid that fills over two seconds feels
alive and one that appears at once after four feels broken.
"""

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence

import structlog

from glia.config import Settings
from glia.contracts import Candidate, CandidatesBatch
from glia.discovery.cala import CalaCitedLane, CalaClient
from glia.discovery.commons import CommonsLane
from glia.discovery.fetch import DocumentFetcher
from glia.discovery.lane import ImageLane, LaneUnavailable
from glia.discovery.merge import proxied, select_new
from glia.discovery.openverse import OpenverseLane

logger = structlog.get_logger(__name__)

Emit = Callable[[CandidatesBatch], Awaitable[None]]

FIXTURE_CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        id="commons:79679",
        lane="open",
        image_url="https://upload.wikimedia.org/wikipedia/commons/2/27/Ing_telescopes_sunset_la"
        "_palma_july_2001.jpg",
        source_url="https://commons.wikimedia.org/wiki/File:Ing_telescopes_sunset_la_palma_july_2001.jpg",
        publisher="Wikimedia Commons",
        title="Ing telescopes sunset la palma july 2001",
        licence="Public domain",
        width=800,
        height=533,
        score=1.0,
    ),
    Candidate(
        id="openverse:13fdd54c-1cf7-45c9-9145-75fa262ab4d1",
        lane="open",
        image_url="https://live.staticflickr.com/52/126245219_3326117a1b.jpg",
        source_url="https://www.flickr.com/photos/79727841@N00/126245219",
        publisher="flickr",
        title="Observatory Tower, Lincoln Castle",
        licence="BY-SA 2.0",
        width=500,
        height=388,
        score=1.0,
    ),
    Candidate(
        id="commons:71452798",
        lane="open",
        image_url="https://upload.wikimedia.org/wikipedia/commons/thumb/b/b8/Laser_Towards_Milk"
        "y_Ways_Centre.jpg/960px-Laser_Towards_Milky_Ways_Centre.jpg",
        source_url="https://commons.wikimedia.org/wiki/File:Laser_Towards_Milky_Ways_Centre.jpg",
        publisher="Wikimedia Commons",
        title="Laser Towards Milky Ways Centre",
        licence="CC BY 4.0",
        width=800,
        height=726,
        score=0.9954,
    ),
    Candidate(
        id="openverse:ca1a8aa2-ad98-48d0-9475-2ef6f4691b17",
        lane="open",
        image_url="https://live.staticflickr.com/1096/1026606495_9f8e8d170a_b.jpg",
        source_url="https://www.flickr.com/photos/56796376@N00/1026606495",
        publisher="flickr",
        title="India - Jaipur - 006 - sundial close-up at the Jantar Mantar observatory",
        licence="BY 2.0",
        width=768,
        height=1024,
        score=0.998,
    ),
    Candidate(
        id="commons:61475151",
        lane="open",
        image_url="https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/Kopenhagen_%28DK%2"
        "9%2C_Runder_Turm_--_2017_--_1633.jpg/960px-"
        "Kopenhagen_%28DK%29%2C_Runder_Turm_--_2017_--_1633.jpg",
        source_url="https://commons.wikimedia.org/wiki/File:Kopenhagen_(DK),_Runder_Turm_--_2017_--"
        "_1633.jpg",
        publisher="Wikimedia Commons",
        title="Kopenhagen (DK), Runder Turm -- 2017 -- 1633",
        licence="CC BY-SA 4.0",
        width=800,
        height=533,
        score=0.9333,
    ),
    Candidate(
        id="openverse:02b97c64-4c7f-44b1-8809-4ba99b1fc0a4",
        lane="open",
        image_url="https://live.staticflickr.com/1149/1026583267_78e952aa27_b.jpg",
        source_url="https://www.flickr.com/photos/56796376@N00/1026583267",
        publisher="flickr",
        title="India - Jaipur - 002 - Jantar Mantar Observatory",
        licence="BY 2.0",
        width=1024,
        height=768,
        score=0.948,
    ),
    Candidate(
        id="commons:34872620",
        lane="open",
        image_url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/ad/Observatorio_Mojon"
        "_del_Trigo_2014-08-07.jpg/960px-Observatorio_Mojon_del_Trigo_2014-08-07.jpg",
        source_url="https://commons.wikimedia.org/wiki/File:Observatorio_Mojon_del_Trigo_2014-08-07.jpg",
        publisher="Wikimedia Commons",
        title="Observatorio Mojon del Trigo 2014-08-07",
        licence="CC BY-SA 3.0",
        width=800,
        height=516,
        score=0.8822,
    ),
    Candidate(
        id="openverse:f9f85f0a-aa3e-42c2-aaf4-7299dec534b8",
        lane="open",
        image_url="https://live.staticflickr.com/6080/6060947569_1bd8e8b2d3_b.jpg",
        source_url="https://www.flickr.com/photos/24413864@N05/6060947569",
        publisher="flickr",
        title="Sphinx Observatory",
        licence="BY 2.0",
        width=1024,
        height=575,
        score=0.8859,
    ),
)


class DiscoveryService:
    def __init__(
        self,
        *,
        lanes: tuple[ImageLane, ...],
        proxy_base: str,
        min_edge: int,
        max_candidates: int,
        wave_size: int,
        wave_delay_seconds: float,
        lane_timeout_seconds: float,
        lane_stagger_seconds: float,
        lane_min_results: int,
        lane_max_attempts: int,
        allowlist: tuple[str, ...],
        cache_size: int,
        cala_lane_timeout_seconds: float | None = None,
    ) -> None:
        self._lanes = lanes
        self._proxy_base = proxy_base
        self._min_edge = min_edge
        self._max_candidates = max_candidates
        self._wave_size = wave_size
        self._wave_delay = wave_delay_seconds
        self._lane_timeout = lane_timeout_seconds
        self._lane_stagger = lane_stagger_seconds
        self._lane_min_results = lane_min_results
        self._lane_max_attempts = lane_max_attempts
        self._allowlist = allowlist
        self._cache_size = cache_size
        self._cala_lane_timeout = cala_lane_timeout_seconds or lane_timeout_seconds
        self._cache: OrderedDict[str, list[Candidate]] = OrderedDict()

    async def discover(
        self,
        *,
        queries: Sequence[str],
        revision: int,
        emit: Emit,
        include_cited: bool = True,
    ) -> list[Candidate]:
        """Emit waves for one query ladder and return everything that shipped."""
        ladder = tuple(query for query in queries if query)
        if not ladder:
            return []

        lanes = tuple(
            lane for lane in self._lanes if include_cited or lane.name != "cala"
        )
        if not lanes:
            return []

        # An optimistic open-only result must never satisfy the settled cache lookup: doing so
        # would silently skip Cala after the user pauses. Keep the two paths independently warm.
        cache_key = f"{'all' if include_cited else 'open'}:{ladder[0]}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache.move_to_end(cache_key)
            await self._emit_waves(cached, revision=revision, emit=emit)
            return cached

        queue: asyncio.Queue[list[Candidate]] = asyncio.Queue()
        shipped: list[Candidate] = []
        async with asyncio.TaskGroup() as group:
            for lane in lanes:
                group.create_task(self._run_lane(lane, ladder, queue))
            group.create_task(self._drain(queue, len(lanes), revision, emit, shipped))

        self._remember(cache_key, shipped)
        return shipped

    async def _run_lane(
        self, lane: ImageLane, ladder: tuple[str, ...], queue: asyncio.Queue[list[Candidate]]
    ) -> None:
        """Walk the ladder until the lane has enough, then report.

        A lane never raises into the group: a dead lane is an empty lane, and
        the other lane still fills the grid.
        """
        candidates: list[Candidate] = []
        started = asyncio.get_running_loop().time()
        try:
            lane_timeout = self._cala_lane_timeout if lane.name == "cala" else self._lane_timeout
            max_attempts = 1 if lane.name == "cala" else self._lane_max_attempts
            async with asyncio.timeout(lane_timeout):
                for attempt, query in enumerate(ladder[:max_attempts]):
                    elapsed = asyncio.get_running_loop().time() - started
                    # Never start a rung that cannot plausibly finish: a broader
                    # rung timing out would throw away what a sharper one found.
                    if attempt and elapsed > lane_timeout / 2:
                        break
                    found = await lane.search(query)
                    # A broader rung may return more items but be less relevant. Preserve the
                    # sharp results and only fill the remaining slots with broader candidates.
                    seen_ids = {candidate.id for candidate in candidates}
                    candidates.extend(
                        candidate for candidate in found if candidate.id not in seen_ids
                    )
                    if len(candidates) >= self._lane_min_results:
                        break
        except (LaneUnavailable, TimeoutError) as error:
            logger.warning("discovery.lane_failed", lane=lane.name, error=type(error).__name__)
        except Exception as error:  # a lane must never cancel its sibling
            logger.warning("discovery.lane_crashed", lane=lane.name, error=type(error).__name__)
        await queue.put(candidates)

    async def _drain(
        self,
        queue: asyncio.Queue[list[Candidate]],
        lane_count: int,
        revision: int,
        emit: Emit,
        shipped: list[Candidate],
    ) -> None:
        seen: set[str] = set()
        remaining = lane_count
        while remaining > 0 and len(shipped) < self._max_candidates:
            batch = [await queue.get()]
            remaining -= 1
            # Give a slower lane a short grace period so the first wave is mixed
            # rather than one lane's twenty results followed by the other's.
            while remaining > 0:
                try:
                    async with asyncio.timeout(self._lane_stagger):
                        batch.append(await queue.get())
                except TimeoutError:
                    break
                remaining -= 1
            selected = select_new(
                batch,
                seen=seen,
                min_edge=self._min_edge,
                allowlist=self._allowlist,
                limit=self._max_candidates - len(shipped),
            )
            if not selected:
                continue
            shipped.extend(selected)
            await self._emit_waves(selected, revision=revision, emit=emit)

    async def _emit_waves(self, candidates: list[Candidate], *, revision: int, emit: Emit) -> None:
        for index in range(0, len(candidates), self._wave_size):
            wave = candidates[index : index + self._wave_size]
            await emit(
                CandidatesBatch(
                    revision=revision,
                    candidates=proxied(wave, proxy_base=self._proxy_base),
                )
            )
            if index + self._wave_size < len(candidates) and self._wave_delay > 0:
                await asyncio.sleep(self._wave_delay)

    def _remember(self, query: str, candidates: list[Candidate]) -> None:
        if not candidates:
            return
        self._cache[query] = candidates
        self._cache.move_to_end(query)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)


class FixtureImageLane:
    """Canned results for demo_mode=fixture. Touches no network."""

    @property
    def name(self) -> str:
        return "fixture"

    async def search(self, query: str) -> list[Candidate]:
        return list(FIXTURE_CANDIDATES)


def build_discovery_service(
    settings: Settings, *, cala_client: CalaClient | None = None
) -> DiscoveryService:
    lanes: tuple[ImageLane, ...]
    if settings.demo_mode == "fixture":
        lanes = (FixtureImageLane(),)
    else:
        open_lanes: tuple[ImageLane, ...] = (
            CommonsLane(
                api_url=settings.commons_api_url,
                user_agent=settings.image_fetch_user_agent,
                page_size=settings.discovery_page_size,
                timeout_seconds=settings.discovery_lane_timeout_seconds,
                max_retries=settings.discovery_max_retries,
            ),
            OpenverseLane(
                base_url=settings.openverse_base_url,
                user_agent=settings.image_fetch_user_agent,
                page_size=settings.discovery_page_size,
                timeout_seconds=settings.discovery_lane_timeout_seconds,
                max_retries=settings.discovery_max_retries,
                client_id=(
                    settings.openverse_client_id.get_secret_value()
                    if settings.openverse_client_id
                    else None
                ),
                client_secret=(
                    settings.openverse_client_secret.get_secret_value()
                    if settings.openverse_client_secret
                    else None
                ),
            ),
        )
        if cala_client is not None and cala_client.configured:
            lanes = (
                CalaCitedLane(
                    client=cala_client,
                    document_fetcher=DocumentFetcher(
                        user_agent=settings.image_fetch_user_agent,
                        max_bytes=settings.image_fetch_max_bytes,
                        connect_timeout=settings.image_fetch_connect_timeout,
                        total_timeout=settings.image_fetch_total_timeout,
                    ),
                    min_seconds_between_queries=settings.cala_min_seconds_between_queries,
                ),
                *open_lanes,
            )
        else:
            lanes = open_lanes
    return DiscoveryService(
        lanes=lanes,
        proxy_base=settings.api_base_url,
        min_edge=settings.discovery_min_edge,
        max_candidates=settings.discovery_max_candidates,
        wave_size=settings.discovery_wave_size,
        wave_delay_seconds=settings.discovery_wave_delay_seconds,
        lane_timeout_seconds=settings.discovery_lane_timeout_seconds,
        lane_stagger_seconds=settings.discovery_lane_stagger_seconds,
        lane_min_results=settings.discovery_lane_min_results,
        lane_max_attempts=settings.discovery_lane_max_attempts,
        allowlist=settings.image_host_allowlist,
        cache_size=settings.discovery_cache_size,
        cala_lane_timeout_seconds=(
            settings.cala_request_timeout_seconds + settings.image_fetch_total_timeout
        ),
    )
