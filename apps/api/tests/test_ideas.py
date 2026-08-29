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
async def test_local_ideas_use_the_deterministic_query_ladder_as_search_queries() -> None:
    intent = VisualIntent(subject="manzanas verdes", moods=[], styles=[], palette=["verde"])

    result = await LocalIdeaSynthesizer().synthesize("Quiero manzanas verdes", intent)

    assert result.search_queries == ["green apples", "apples"]
    assert merge_idea_queries(intent, result) == ("green apples", "apples")
