from glia.contracts import VisualIntent
from glia.discovery.query import build_preview_queries, build_queries


def intent(
    subject: str,
    *,
    styles: list[str] | None = None,
    moods: list[str] | None = None,
    palette: list[str] | None = None,
) -> VisualIntent:
    return VisualIntent(
        subject=subject,
        moods=moods or [],
        styles=styles or [],
        palette=palette or [],
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


def test_ladder_does_not_broaden_a_named_company_to_generic_headquarters() -> None:
    assert build_queries(intent("Klarna headquarters", styles=["cinematic"])) == (
        "klarna cinematic",
        "klarna",
    )


def test_ladder_deduplicates_reconciled_realtime_words() -> None:
    assert build_queries(intent("gatos gatos perros")) == ("cats dogs", "dogs")


def test_ladder_uses_unambiguous_english_alias_and_palette_for_cars() -> None:
    assert build_queries(intent("coches", palette=["blue"])) == ("blue cars", "cars")


def test_ladder_aliases_common_live_demo_subjects() -> None:
    assert build_queries(intent("gatos")) == ("cats",)
    assert build_queries(intent("perros")) == ("dogs",)
    assert build_queries(intent("manzanas verdes")) == ("green apples", "apples")


def test_aliases_are_exact_and_do_not_rewrite_longer_names() -> None:
    assert build_queries(intent("Coches de Caracas")) == ("coches caracas", "caracas")


def test_ladder_normalises_common_non_english_palette_terms() -> None:
    assert build_queries(intent("cotxes", palette=["blau"])) == ("blue cars", "cars")
    assert build_queries(intent("coches", palette=["color azul"])) == ("blue cars", "cars")


def test_ladder_turns_spanish_military_plane_into_a_photographic_query() -> None:
    assert build_queries(intent("avioneta de militar")) == (
        "military aircraft",
        "aircraft",
    )


def test_preview_maps_minimalist_outlets_to_findable_english_concepts() -> None:
    expected = (
        "electrical outlets",
        "wall sockets",
        "power sockets",
    )
    assert build_preview_queries(intent("enchufes minimalistas")) == expected
    assert build_preview_queries(intent("endolls minimalistes")) == expected
    assert build_preview_queries(intent("minimalist electrical outlets")) == expected


def test_preview_can_take_minimalist_direction_from_structured_style() -> None:
    assert build_preview_queries(intent("enchufes", styles=["minimalistas"])) == (
        "electrical outlets",
        "wall sockets",
        "power sockets",
    )


def test_preview_keeps_known_demo_concepts_fast() -> None:
    assert build_preview_queries(intent("gatos y perros")) == ("cats dogs", "dogs")
    assert build_preview_queries(intent("manzanas verdes")) == ("green apples", "apples")


def test_preview_does_not_search_unknown_or_project_compounds_literally() -> None:
    assert build_preview_queries(intent("club ticketing ui", styles=["minimalist"])) == ()
    assert build_preview_queries(intent("fuera para comprar tickets clubs")) == ()
