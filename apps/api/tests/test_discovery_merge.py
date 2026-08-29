from glia.contracts import Candidate
from glia.discovery.merge import interleave, is_servable, proxied, select_new

ALLOWLIST = ("upload.wikimedia.org", "staticflickr.com")


def candidate(
    identifier: str,
    *,
    image_url: str = "https://upload.wikimedia.org/a.jpg",
    source_url: str = "https://commons.wikimedia.org/wiki/File:A.jpg",
    title: str | None = None,
    width: int | None = 800,
    height: int | None = 600,
) -> Candidate:
    return Candidate(
        id=identifier,
        lane="open",
        image_url=image_url,
        source_url=source_url,
        title=title,
        width=width,
        height=height,
        score=1.0,
    )


def test_a_candidate_without_dimensions_is_dropped() -> None:
    # Reserved aspect boxes need real dimensions; a tile that reflows on load
    # is the failure this design exists to avoid.
    assert not is_servable(candidate("a", width=None), min_edge=200, allowlist=ALLOWLIST)
    assert not is_servable(candidate("b", height=None), min_edge=200, allowlist=ALLOWLIST)


def test_a_candidate_under_the_minimum_edge_is_dropped() -> None:
    assert not is_servable(candidate("a", width=199), min_edge=200, allowlist=ALLOWLIST)
    assert not is_servable(candidate("b", height=120), min_edge=200, allowlist=ALLOWLIST)
    assert is_servable(candidate("c", width=200, height=200), min_edge=200, allowlist=ALLOWLIST)


def test_a_candidate_that_is_not_http_or_https_is_dropped() -> None:
    assert not is_servable(
        candidate("a", image_url="ftp://upload.wikimedia.org/a.jpg"),
        min_edge=200,
        allowlist=ALLOWLIST,
    )
    assert not is_servable(
        candidate("b", source_url="javascript:alert(1)"), min_edge=200, allowlist=ALLOWLIST
    )


def test_a_candidate_we_could_not_serve_through_the_proxy_is_dropped() -> None:
    assert not is_servable(
        candidate("a", image_url="https://images.example.com/a.jpg"),
        min_edge=200,
        allowlist=ALLOWLIST,
    )


def test_lanes_are_interleaved_so_a_wave_is_mixed() -> None:
    left = [candidate("l1"), candidate("l2"), candidate("l3")]
    right = [candidate("r1"), candidate("r2")]

    assert [item.id for item in interleave([left, right])] == ["l1", "r1", "l2", "r2", "l3"]


def test_duplicate_urls_and_titles_are_dropped_across_lanes() -> None:
    seen: set[str] = set()
    left = [
        candidate("l1", image_url="https://upload.wikimedia.org/a.jpg", title="Observatory"),
        candidate("l2", image_url="https://upload.wikimedia.org/b.jpg", title="Tower"),
    ]
    right = [
        # Same image behind tracking params and a different case of host.
        candidate(
            "r1",
            image_url="https://UPLOAD.wikimedia.org/a.jpg?utm_source=commons",
            title="Something else",
        ),
        # Same title, different image: a near-duplicate of the same subject.
        candidate("r2", image_url="https://upload.wikimedia.org/c.jpg", title="observatory!"),
        candidate("r3", image_url="https://upload.wikimedia.org/d.jpg", title="Sundial"),
    ]

    selected = select_new(
        [left, right], seen=seen, min_edge=200, allowlist=ALLOWLIST, limit=20
    )

    assert [item.id for item in selected] == ["l1", "r3", "l2"]


def test_selection_is_capped_and_remembers_what_already_shipped() -> None:
    seen: set[str] = set()
    lane = [
        candidate(f"c{index}", image_url=f"https://upload.wikimedia.org/{index}.jpg")
        for index in range(5)
    ]

    first = select_new([lane], seen=seen, min_edge=200, allowlist=ALLOWLIST, limit=2)
    second = select_new([lane], seen=seen, min_edge=200, allowlist=ALLOWLIST, limit=5)

    assert [item.id for item in first] == ["c0", "c1"]
    assert [item.id for item in second] == ["c2", "c3", "c4"]


def test_the_proxy_rewrite_keeps_the_origin_as_source_url() -> None:
    original = candidate("a", image_url="https://upload.wikimedia.org/a b.jpg?x=1")

    rewritten = proxied([original], proxy_base="https://api.glia.test/")[0]

    assert rewritten.image_url == (
        "https://api.glia.test/api/image?url="
        "https%3A%2F%2Fupload.wikimedia.org%2Fa%20b.jpg%3Fx%3D1"
    )
    assert rewritten.source_url == original.source_url
