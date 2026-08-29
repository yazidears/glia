import asyncio

import pytest

from glia.config import Settings
from glia.contracts import Candidate, CandidatesBatch
from glia.discovery.lane import LaneUnavailable
from glia.discovery.service import (
    FIXTURE_CANDIDATES,
    DiscoveryService,
    build_discovery_service,
)

ALLOWLIST = ("upload.wikimedia.org", "staticflickr.com")


def candidate(identifier: str) -> Candidate:
    return Candidate(
        id=identifier,
        lane="open",
        image_url=f"https://upload.wikimedia.org/{identifier}.jpg",
        source_url=f"https://commons.wikimedia.org/wiki/File:{identifier}.jpg",
        title=identifier,
        licence="CC BY-SA 4.0",
        width=800,
        height=600,
        score=1.0,
    )


class StubLane:
    def __init__(
        self,
        name: str,
        results: dict[str, list[Candidate]],
        *,
        fails: bool = False,
        delay: float = 0.0,
    ) -> None:
        self._name = name
        self._results = results
        self._fails = fails
        self._delay = delay
        self.queries: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    async def search(self, query: str) -> list[Candidate]:
        self.queries.append(query)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._fails:
            raise LaneUnavailable(self._name)
        return self._results.get(query, [])


def service(*lanes: StubLane, **overrides: float | int) -> DiscoveryService:
    settings: dict[str, float | int] = {
        "min_edge": 200,
        "max_candidates": 30,
        "wave_size": 4,
        "wave_delay_seconds": 0.0,
        "lane_timeout_seconds": 1.0,
        "lane_min_results": 4,
        "lane_max_attempts": 3,
        "cache_size": 8,
    }
    settings.update(overrides)
    return DiscoveryService(
        lanes=tuple(lanes),
        proxy_base="https://api.glia.test",
        allowlist=ALLOWLIST,
        min_edge=int(settings["min_edge"]),
        max_candidates=int(settings["max_candidates"]),
        wave_size=int(settings["wave_size"]),
        wave_delay_seconds=float(settings["wave_delay_seconds"]),
        lane_timeout_seconds=float(settings["lane_timeout_seconds"]),
        lane_min_results=int(settings["lane_min_results"]),
        lane_max_attempts=int(settings["lane_max_attempts"]),
        cache_size=int(settings["cache_size"]),
    )


class Collector:
    def __init__(self) -> None:
        self.batches: list[CandidatesBatch] = []

    async def __call__(self, batch: CandidatesBatch) -> None:
        self.batches.append(batch)

    @property
    def ids(self) -> list[str]:
        return [item.id for batch in self.batches for item in batch.candidates]


@pytest.mark.asyncio
async def test_both_lanes_run_and_the_first_wave_is_mixed() -> None:
    left = StubLane("commons", {"observatory": [candidate(f"c{index}") for index in range(4)]})
    right = StubLane("openverse", {"observatory": [candidate(f"o{index}") for index in range(4)]})
    collector = Collector()

    shipped = await service(left, right).discover(
        queries=("observatory",), revision=3, emit=collector
    )

    assert len(shipped) == 8
    assert {batch.revision for batch in collector.batches} == {3}
    assert collector.ids[:4] == ["c0", "o0", "c1", "o1"]


@pytest.mark.asyncio
async def test_results_arrive_as_waves_rather_than_one_batch() -> None:
    lane = StubLane("commons", {"observatory": [candidate(f"c{index}") for index in range(10)]})
    collector = Collector()

    await service(lane, wave_size=4).discover(queries=("observatory",), revision=1, emit=collector)

    assert [len(batch.candidates) for batch in collector.batches] == [4, 4, 2]


@pytest.mark.asyncio
async def test_a_dead_lane_degrades_to_the_other_lane() -> None:
    dead = StubLane("commons", {}, fails=True)
    alive = StubLane("openverse", {"observatory": [candidate(f"o{index}") for index in range(4)]})
    collector = Collector()

    shipped = await service(dead, alive).discover(
        queries=("observatory",), revision=1, emit=collector
    )

    assert [item.id for item in shipped] == ["o0", "o1", "o2", "o3"]


@pytest.mark.asyncio
async def test_a_hanging_lane_does_not_hold_up_the_other_lane() -> None:
    slow = StubLane("commons", {"observatory": [candidate("c0")]}, delay=5.0)
    fast = StubLane("openverse", {"observatory": [candidate(f"o{index}") for index in range(4)]})
    collector = Collector()

    shipped = await service(slow, fast, lane_timeout_seconds=0.2).discover(
        queries=("observatory",), revision=1, emit=collector
    )

    assert [item.id for item in shipped] == ["o0", "o1", "o2", "o3"]


@pytest.mark.asyncio
async def test_a_lane_broadens_down_the_ladder_until_it_has_enough() -> None:
    lane = StubLane(
        "commons",
        {"observatory": [candidate(f"c{index}") for index in range(4)]},
    )
    collector = Collector()

    await service(lane).discover(
        queries=("brutalist observatory cinematic", "brutalist observatory", "observatory"),
        revision=1,
        emit=collector,
    )

    assert lane.queries == [
        "brutalist observatory cinematic",
        "brutalist observatory",
        "observatory",
    ]
    assert len(collector.ids) == 4


@pytest.mark.asyncio
async def test_a_lane_stops_climbing_once_a_rung_returned_enough() -> None:
    lane = StubLane(
        "commons",
        {"brutalist observatory": [candidate(f"c{index}") for index in range(4)]},
    )

    await service(lane).discover(
        queries=("brutalist observatory cinematic", "brutalist observatory", "observatory"),
        revision=1,
        emit=Collector(),
    )

    assert lane.queries == ["brutalist observatory cinematic", "brutalist observatory"]


@pytest.mark.asyncio
async def test_broadening_preserves_the_sharp_results() -> None:
    sharp = candidate("sharp")
    broad = [candidate(f"broad-{index}") for index in range(4)]
    lane = StubLane(
        "commons",
        {
            "minimalist electrical outlet": [sharp],
            "electrical outlets": broad,
        },
    )
    collector = Collector()

    await service(lane).discover(
        queries=("minimalist electrical outlet", "electrical outlets"),
        revision=1,
        emit=collector,
    )

    assert collector.ids == ["sharp", *(item.id for item in broad)]


@pytest.mark.asyncio
async def test_the_same_subject_twice_is_served_from_cache() -> None:
    lane = StubLane("commons", {"observatory": [candidate(f"c{index}") for index in range(4)]})
    discovery = service(lane)
    first = Collector()
    second = Collector()

    await discovery.discover(queries=("observatory",), revision=1, emit=first)
    await discovery.discover(queries=("observatory",), revision=9, emit=second)

    assert lane.queries == ["observatory"]
    assert first.ids == second.ids
    assert {batch.revision for batch in second.batches} == {9}


@pytest.mark.asyncio
async def test_open_preview_skips_cala_without_poisoning_the_settled_cache() -> None:
    cala = StubLane("cala", {"green apples": [candidate("cited")]})
    commons = StubLane("commons", {"green apples": [candidate("open")]})
    discovery = service(cala, commons)

    await discovery.discover(
        queries=("green apples",),
        revision=1,
        emit=Collector(),
        include_cited=False,
    )
    await discovery.discover(
        queries=("green apples",),
        revision=2,
        emit=Collector(),
        include_cited=True,
    )

    assert cala.queries == ["green apples"]
    assert commons.queries == ["green apples", "green apples"]


@pytest.mark.asyncio
async def test_an_empty_ladder_never_reaches_a_lane() -> None:
    lane = StubLane("commons", {})
    collector = Collector()

    assert await service(lane).discover(queries=(), revision=1, emit=collector) == []
    assert lane.queries == []
    assert collector.batches == []


@pytest.mark.asyncio
async def test_emitted_candidates_are_served_through_the_proxy() -> None:
    lane = StubLane("commons", {"observatory": [candidate("c0")]})
    collector = Collector()

    await service(lane).discover(queries=("observatory",), revision=1, emit=collector)

    emitted = collector.batches[0].candidates[0]
    assert emitted.image_url.startswith("https://api.glia.test/api/image?url=")
    assert emitted.source_url == "https://commons.wikimedia.org/wiki/File:c0.jpg"


@pytest.mark.asyncio
async def test_fixture_mode_emits_a_batch_without_touching_the_network() -> None:
    discovery = build_discovery_service(Settings(demo_mode="fixture"))
    collector = Collector()

    shipped = await discovery.discover(queries=("anything",), revision=1, emit=collector)

    assert len(shipped) == len(FIXTURE_CANDIDATES)
    assert collector.batches
    assert all(item.licence and item.width and item.height for item in shipped)


@pytest.mark.asyncio
async def test_a_slow_lane_never_delays_the_other_lanes_first_wave() -> None:
    """The failure this ticket exists for: one lane's latency held the whole grid.

    The fast lane's candidates must be on the wire while the slow lane is still
    walking its ladder, not after it finishes.
    """
    slow = StubLane("commons", {"observatory": [candidate("c0")]}, delay=0.4)
    fast = StubLane("openverse", {"observatory": [candidate(f"o{index}") for index in range(4)]})

    first_wave_at: list[float] = []

    class Timed(Collector):
        async def __call__(self, batch: CandidatesBatch) -> None:
            first_wave_at.append(asyncio.get_running_loop().time() - started)
            await super().__call__(batch)

    collector = Timed()
    started = asyncio.get_running_loop().time()
    await service(slow, fast, lane_timeout_seconds=2.0).discover(
        queries=("observatory",), revision=1, emit=collector
    )

    assert collector.ids[:4] == ["o0", "o1", "o2", "o3"]
    assert first_wave_at[0] < 0.3, "the fast lane waited for the slow one"


@pytest.mark.asyncio
async def test_every_lane_reports_its_health_after_a_run() -> None:
    alive = StubLane("openverse", {"observatory": [candidate("o0")]})
    dead = StubLane("commons", {}, fails=True)
    instance = service(dead, alive)

    await instance.discover(queries=("observatory",), revision=1, emit=Collector())
    health = {report.lane: report for report in await instance.probe()}

    assert health["commons"].status == "unavailable"
    assert health["openverse"].status == "ok"
    assert health["openverse"].count == 1


@pytest.mark.asyncio
async def test_a_lane_nobody_has_exercised_is_probed() -> None:
    """A lane with no observed traffic is asked, not reported as unknown."""
    lane = StubLane("openverse", {"observatory": [candidate("o0")]})
    instance = service(lane)

    health = await instance.probe()

    assert [report.status for report in health] == ["ok"]
    assert lane.queries == ["observatory"]


@pytest.mark.asyncio
async def test_health_probe_never_spends_a_cala_credit() -> None:
    cala = StubLane("cala", {"observatory": [candidate("cited")]})
    commons = StubLane("commons", {"observatory": [candidate("open")]})
    instance = service(cala, commons)

    health = {report.lane: report for report in await instance.probe()}

    assert cala.queries == []
    assert health["cala"].status == "unknown"
    assert commons.queries == ["observatory"]
    assert health["commons"].status == "ok"


@pytest.mark.asyncio
async def test_a_hanging_lane_reports_a_timeout_rather_than_going_quiet() -> None:
    lane = StubLane("commons", {"observatory": [candidate("c0")]}, delay=5.0)
    instance = service(lane, lane_timeout_seconds=0.1)

    await instance.discover(queries=("observatory",), revision=1, emit=Collector())

    assert [report.status for report in await instance.probe()] == ["timeout"]
