from types import SimpleNamespace
from typing import cast

import pytest
from openai import AsyncOpenAI

from glia.contracts import VisualIntent
from glia.realtime.ideas import LocalIdeaSynthesizer, OpenAIIdeaSynthesizer, merge_idea_queries


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def parse(self, **request: object) -> SimpleNamespace:
        self.calls.append(request)
        payload_type = request["text_format"]
        payload = payload_type(  # type: ignore[operator]
            ideas=[
                "Manzanas verdes sobre fondo blanco",
                "Canasta de manzanas en un huerto",
                "Primer plano de piel brillante",
            ],
            keywords=["manzanas verdes", "canasta de manzanas"],
            search_queries=["green apples product photography", "green apple orchard"],
        )
        return SimpleNamespace(output_parsed=payload)


@pytest.mark.asyncio
async def test_openai_ideas_are_structured_cached_and_become_search_queries() -> None:
    responses = FakeResponses()
    client = cast(AsyncOpenAI, SimpleNamespace(responses=responses))
    synthesizer = OpenAIIdeaSynthesizer(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=1,
        cache_size=4,
        client=client,
    )
    intent = VisualIntent(
        subject="manzanas verdes",
        moods=[],
        styles=[],
        palette=["verde"],
    )

    first = await synthesizer.synthesize("Quiero unas manzanas verdes", intent)
    second = await synthesizer.synthesize("Quiero unas manzanas verdes", intent)

    assert first == second
    assert first.source == "openai"
    assert len(responses.calls) == 1
    assert responses.calls[0]["store"] is False
    assert responses.calls[0]["service_tier"] == "fast"
    assert merge_idea_queries(intent, first) == (
        "green apples product photography",
        "green apple orchard",
        "green apples",
        "apples",
    )


@pytest.mark.asyncio
async def test_search_planner_keeps_ui_language_but_searches_concrete_english_concepts() -> None:
    responses = FakeResponses()

    async def parse(**request: object) -> SimpleNamespace:
        responses.calls.append(request)
        payload_type = request["text_format"]
        payload = payload_type(  # type: ignore[operator]
            ideas=[
                "Enchufe blanco integrado en una pared limpia",
                "Detalle de materiales y juntas discretas",
                "Sistema modular para interiores contemporáneos",
            ],
            keywords=["enchufe", "minimalista", "pared blanca"],
            search_queries=[
                "minimalist electrical outlet product design",
                "wall socket industrial design",
            ],
        )
        return SimpleNamespace(output_parsed=payload)

    responses.parse = parse  # type: ignore[method-assign]
    client = cast(AsyncOpenAI, SimpleNamespace(responses=responses))
    synthesizer = OpenAIIdeaSynthesizer(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=1,
        cache_size=4,
        client=client,
    )
    intent = VisualIntent(
        subject="enchufes minimalistas",
        moods=[],
        styles=["minimalistas"],
        palette=[],
    )

    result = await synthesizer.synthesize(
        "Tengo una idea de hacer enchufes minimalistas.", intent
    )

    assert result.ideas[0].startswith("Enchufe")
    assert result.keywords == ["enchufe", "minimalista", "pared blanca"]
    assert merge_idea_queries(intent, result)[:2] == (
        "minimalist electrical outlet product design",
        "wall socket industrial design",
    )
    instructions = cast(str, responses.calls[0]["instructions"])
    assert "concise English search_queries" in instructions
    assert "do not concatenate" in instructions


@pytest.mark.asyncio
async def test_openai_planner_tolerates_missing_ui_fields_and_uses_intent_copy() -> None:
    responses = FakeResponses()

    async def parse(**request: object) -> SimpleNamespace:
        responses.calls.append(request)
        payload_type = request["text_format"]
        payload = payload_type(  # type: ignore[operator]
            search_queries=["Mediterranean clothing", "Mediterranean fashion"],
            provider_metadata="new field",
        )
        return SimpleNamespace(output_parsed=payload)

    responses.parse = parse  # type: ignore[method-assign]
    client = cast(AsyncOpenAI, SimpleNamespace(responses=responses))
    synthesizer = OpenAIIdeaSynthesizer(
        api_key="test-key",
        model="gpt-5.6-luna",
        timeout_seconds=1,
        cache_size=4,
        client=client,
    )
    intent = VisualIntent(
        subject="textil",
        moods=["tranquilo"],
        styles=[],
        palette=[],
    )

    result = await synthesizer.synthesize("Una marca mediterránea", intent)

    assert result.ideas == ["textil", "tranquilo"]
    assert result.keywords == ["textil", "tranquilo"]
    assert result.search_queries == ["Mediterranean clothing", "Mediterranean fashion"]


@pytest.mark.asyncio
async def test_local_ideas_use_the_deterministic_query_ladder_as_search_queries() -> None:
    intent = VisualIntent(subject="manzanas verdes", moods=[], styles=[], palette=["verde"])

    result = await LocalIdeaSynthesizer().synthesize("Quiero manzanas verdes", intent)

    assert result.search_queries == ["green apples", "apples"]
    assert merge_idea_queries(intent, result) == ("green apples", "apples")


@pytest.mark.asyncio
async def test_local_fallback_uses_company_context_instead_of_literal_current_word() -> None:
    transcript = (
        "Quiero hacer una ropa de marca mediterránea. Entonces quiero que la marca refleje "
        "el estilo de vida del Mediterráneo y el textil debería ser tranquilo."
    )
    intent = VisualIntent(
        subject="textil",
        moods=["tranquilo"],
        styles=[],
        palette=[],
    )

    result = await LocalIdeaSynthesizer().synthesize(transcript, intent)

    assert result.ideas == ["textil", "tranquilo"]
    assert result.search_queries == [
        "Mediterranean fashion",
        "Mediterranean clothing",
        "Mediterranean lifestyle",
    ]
    assert merge_idea_queries(intent, result) == tuple(result.search_queries)
    assert all("textil" not in query.casefold() for query in result.search_queries)


@pytest.mark.asyncio
async def test_local_fallback_plans_a_concrete_ui_search_from_project_context() -> None:
    transcript = (
        "Estoy diseñando una app y un mockup para comprar tickets y reservar entradas de clubs."
    )
    intent = VisualIntent(subject="interfaz", moods=[], styles=["minimalista"], palette=[])

    result = await LocalIdeaSynthesizer().synthesize(transcript, intent)

    assert result.search_queries == [
        "event ticketing mobile app",
        "nightclub booking app interface",
        "mobile ticket user interface",
    ]


@pytest.mark.asyncio
async def test_local_fallback_yields_no_search_for_unknown_abstract_context() -> None:
    intent = VisualIntent(subject="tranquilo", moods=[], styles=[], palette=[])

    result = await LocalIdeaSynthesizer().synthesize("La idea debería sentirse bien.", intent)

    assert result.search_queries == []
    assert merge_idea_queries(intent, result) == ()


@pytest.mark.asyncio
async def test_local_fallback_keeps_a_concrete_object_searchable_offline() -> None:
    intent = VisualIntent(subject="observatory", moods=["lonely"], styles=[], palette=["cobalt"])

    result = await LocalIdeaSynthesizer().synthesize("A lonely cobalt observatory", intent)

    assert result.search_queries == ["cobalt observatory", "observatory"]
    assert merge_idea_queries(intent, result) == tuple(result.search_queries)
