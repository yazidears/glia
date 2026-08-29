"""Lane B discovery: run the open corpora concurrently and stream waves out.

The lanes are independent by construction — one lane failing degrades the wave
to the other lane rather than emptying the grid — and results are emitted in
small waves as they land, because a grid that fills over two seconds feels
alive and one that appears at once after four feels broken.
"""

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import structlog

from glia.config import Settings
from glia.contracts import Candidate, CandidatesBatch
from glia.discovery.commons import CommonsLane
from glia.discovery.lane import ImageLane, LaneUnavailable
from glia.discovery.merge import proxied, select_new
from glia.discovery.openverse import OpenverseLane

logger = structlog.get_logger(__name__)

Emit = Callable[[CandidatesBatch], Awaitable[None]]

LaneStatus = Literal["ok", "empty", "unavailable", "timeout", "crashed", "unknown"]

#: What a health probe asks a lane for. Common enough that a lane returning nothing for
#: it is broken rather than merely unlucky with the query.
PROBE_QUERY = "observatory"

#: How long a lane outcome observed from real traffic stands in for a health probe. Under
#: this, /health reports what production actually saw; over it, /health goes and asks.
HEALTH_OBSERVATION_TTL_SECONDS = 60.0


@dataclass(frozen=True)
class LaneReport:
    """One lane's outcome for one discovery call."""

    lane: str
    status: LaneStatus
    count: int
    elapsed: float


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
        lane_min_results: int,
        lane_max_attempts: int,
        allowlist: tuple[str, ...],
        cache_size: int,
    ) -> None:
        self._lanes = lanes
        self._proxy_base = proxy_base
        self._min_edge = min_edge
        self._max_candidates = max_candidates
        self._wave_size = wave_size
        self._wave_delay = wave_delay_seconds
        self._lane_timeout = lane_timeout_seconds
        self._lane_min_results = lane_min_results
        self._lane_max_attempts = lane_max_attempts
        self._allowlist = allowlist
        self._cache_size = cache_size
        self._cache: OrderedDict[str, list[Candidate]] = OrderedDict()
        #: Last outcome per lane, so /health can answer without going upstream again.
        self._health: dict[str, tuple[LaneReport, float]] = {}

    async def discover(
        self, *, queries: Sequence[str], revision: int, emit: Emit
    ) -> list[Candidate]:
        """Emit waves for one query ladder and return everything that shipped."""
        ladder = tuple(query for query in queries if query)
        if not ladder:
            return []

        cached = self._cache.get(ladder[0])
        if cached is not None:
            self._cache.move_to_end(ladder[0])
            await self._emit_waves(cached, revision=revision, emit=emit)
            return cached

        queue: asyncio.Queue[tuple[LaneReport, list[Candidate]]] = asyncio.Queue()
        shipped: list[Candidate] = []
        async with asyncio.TaskGroup() as group:
            for lane in self._lanes:
                group.create_task(self._run_lane(lane, ladder, queue))
            group.create_task(self._drain(queue, revision, emit, shipped))

        self._remember(ladder[0], shipped)
        return shipped

    async def _run_lane(
        self,
        lane: ImageLane,
        ladder: tuple[str, ...],
        queue: asyncio.Queue[tuple["LaneReport", list[Candidate]]],
    ) -> None:
        """Walk the ladder until the lane has enough, then report.

        A lane never raises into the group: a dead lane is an empty lane, and
        the other lane still fills the grid. Every rung is logged whatever it
        returned — a lane that goes quiet is how this went unnoticed for an hour,
        and silence is not a status.
        """
        candidates: list[Candidate] = []
        clock = asyncio.get_running_loop().time
        started = clock()
        status: LaneStatus = "empty"
        try:
            async with asyncio.timeout(self._lane_timeout):
                for attempt, query in enumerate(ladder[: self._lane_max_attempts]):
                    elapsed = clock() - started
                    # Never start a rung that cannot plausibly finish: a broader
                    # rung timing out would throw away what a sharper one found.
                    if attempt and elapsed > self._lane_timeout / 2:
                        break
                    rung_started = clock()
                    try:
                        found = await lane.search(query)
                    except LaneUnavailable:
                        self._log_rung(lane, query, "unavailable", 0, clock() - rung_started)
                        raise
                    self._log_rung(
                        lane,
                        query,
                        "ok" if found else "empty",
                        len(found),
                        clock() - rung_started,
                    )
                    if len(found) > len(candidates):
                        candidates = found
                    if len(candidates) >= self._lane_min_results:
                        break
                status = "ok" if candidates else "empty"
        except LaneUnavailable as error:
            status = "unavailable"
            logger.warning("discovery.lane_failed", lane=lane.name, error=type(error).__name__)
        except TimeoutError as error:
            status = "timeout"
            logger.warning("discovery.lane_failed", lane=lane.name, error=type(error).__name__)
        except Exception as error:  # a lane must never cancel its sibling
            status = "crashed"
            logger.warning("discovery.lane_crashed", lane=lane.name, error=type(error).__name__)

        report = LaneReport(
            lane=lane.name, status=status, count=len(candidates), elapsed=clock() - started
        )
        self._remember_health(report)
        logger.info(
            "discovery.lane_done",
            lane=report.lane,
            status=report.status,
            count=report.count,
            elapsed_ms=round(report.elapsed * 1_000),
        )
        await queue.put((report, candidates))

    def _log_rung(
        self, lane: ImageLane, query: str, status: LaneStatus, count: int, elapsed: float
    ) -> None:
        logger.info(
            "discovery.lane_query",
            lane=lane.name,
            query=query,
            status=status,
            count=count,
            elapsed_ms=round(elapsed * 1_000),
        )

    async def _drain(
        self,
        queue: asyncio.Queue[tuple["LaneReport", list[Candidate]]],
        revision: int,
        emit: Emit,
        shipped: list[Candidate],
    ) -> None:
        """Ship each lane's results the moment they land.

        The first lane home is emitted immediately; a second lane that has *also*
        already finished is folded into the same wave, because mixing is free when
        it costs no wall-clock. What is never done is waiting: a slow or dead lane
        must not hold the other lane's first wave, which is the whole point of
        running them independently.
        """
        seen: set[str] = set()
        remaining = len(self._lanes)
        while remaining > 0 and len(shipped) < self._max_candidates:
            batch = [(await queue.get())[1]]
            remaining -= 1
            # One event-loop turn, not a delay: it lets a lane that finished in the
            # same tick enqueue, and returns instantly when none has.
            await asyncio.sleep(0)
            while remaining > 0:
                try:
                    batch.append(queue.get_nowait()[1])
                except asyncio.QueueEmpty:
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

    # ── health ──────────────────────────────────────────────────────────────
    #
    # A dead lane must be visible without reading logs. Real traffic is the best
    # probe there is, so an outcome seen in the last minute answers /health for
    # free; only a lane nobody has exercised recently is actually asked.

    def _remember_health(self, report: LaneReport) -> None:
        self._health[report.lane] = (report, asyncio.get_running_loop().time())

    @property
    def lane_names(self) -> tuple[str, ...]:
        return tuple(lane.name for lane in self._lanes)

    async def probe(self) -> list[LaneReport]:
        """Report every lane's health, asking only the lanes nobody has exercised."""
        now = asyncio.get_running_loop().time()
        stale = [
            lane
            for lane in self._lanes
            if (observed := self._health.get(lane.name)) is None
            or now - observed[1] > HEALTH_OBSERVATION_TTL_SECONDS
        ]
        if stale:
            async with asyncio.TaskGroup() as group:
                for lane in stale:
                    group.create_task(self._probe_lane(lane))
        return [
            observed[0]
            if (observed := self._health.get(lane.name))
            else LaneReport(lane=lane.name, status="unknown", count=0, elapsed=0.0)
            for lane in self._lanes
        ]

    async def _probe_lane(self, lane: ImageLane) -> None:
        clock = asyncio.get_running_loop().time
        started = clock()
        status: LaneStatus = "empty"
        count = 0
        try:
            async with asyncio.timeout(self._lane_timeout):
                found = await lane.search(PROBE_QUERY)
            count = len(found)
            status = "ok" if found else "empty"
        except LaneUnavailable:
            status = "unavailable"
        except TimeoutError:
            status = "timeout"
        except Exception:  # a probe must never take the health endpoint down
            status = "crashed"
        report = LaneReport(lane=lane.name, status=status, count=count, elapsed=clock() - started)
        self._remember_health(report)
        logger.info(
            "discovery.lane_probe",
            lane=report.lane,
            status=report.status,
            count=report.count,
            elapsed_ms=round(report.elapsed * 1_000),
        )

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


def build_discovery_service(settings: Settings) -> DiscoveryService:
    lanes: tuple[ImageLane, ...]
    if settings.demo_mode == "fixture":
        lanes = (FixtureImageLane(),)
    else:
        lanes = (
            CommonsLane(
                api_url=settings.commons_api_url,
                user_agent=settings.image_fetch_user_agent,
                page_size=settings.discovery_page_size,
                timeout_seconds=settings.discovery_request_timeout_seconds,
                max_retries=settings.discovery_max_retries,
            ),
            OpenverseLane(
                base_url=settings.openverse_base_url,
                user_agent=settings.image_fetch_user_agent,
                page_size=settings.discovery_page_size,
                timeout_seconds=settings.discovery_request_timeout_seconds,
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
    return DiscoveryService(
        lanes=lanes,
        proxy_base=settings.api_base_url,
        min_edge=settings.discovery_min_edge,
        max_candidates=settings.discovery_max_candidates,
        wave_size=settings.discovery_wave_size,
        wave_delay_seconds=settings.discovery_wave_delay_seconds,
        lane_timeout_seconds=settings.discovery_lane_timeout_seconds,
        lane_min_results=settings.discovery_lane_min_results,
        lane_max_attempts=settings.discovery_lane_max_attempts,
        allowlist=settings.image_host_allowlist,
        cache_size=settings.discovery_cache_size,
    )
