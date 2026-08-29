from glia.contracts import VisualIntent
from glia.discovery.query import build_queries


def intent(
    subject: str, *, styles: list[str] | None = None, moods: list[str] | None = None
) -> VisualIntent:
    return VisualIntent(
        subject=subject,
        moods=moods or [],
        styles=styles or [],
        palette=[],
    )


def test_ladder_sharpens_a_thin_subject_then_broadens() -> None:
    assert build_queries(intent("observatory", styles=["cinematic"], moods=["lonely"])) == (
        "observatory cinematic",
        "observatory",
    )


def test_ladder_keeps_the_head_noun_when_broadening() -> None:
    # Spoken subjects are head-final: broadening must not leave an adjective.
    assert build_queries(intent("a cold brutalist observatory")) == (
        "cold brutalist observatory",
        "brutalist observatory",
        "observatory",
    )


def test_ladder_skips_the_sharpener_when_the_subject_is_already_long() -> None:
    ladder = build_queries(intent("kyoto temple autumn", styles=["cinematic"]))
    assert ladder[0] == "kyoto temple autumn"
    assert all("cinematic" not in query for query in ladder)


def test_ladder_is_empty_when_nothing_searchable_was_said() -> None:
    assert build_queries(intent("um, a")) == ()
