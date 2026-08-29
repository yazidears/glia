import pytest

from glia.contracts import CalaSearchResult
from glia.discovery.cala import (
    extract_lead_image,
    extract_subject,
    join_evidence,
    visual_entity_for,
    visual_entity_query,
)
from glia.discovery.fetch import TextDocument


def test_cala_contract_keeps_images_out_of_search_results() -> None:
    assert not {"image", "image_url", "thumbnail", "logo", "media"} & set(
        CalaSearchResult.model_fields
    )


def test_cala_subject_and_evidence_helpers_are_source_oriented() -> None:
    result = CalaSearchResult.model_validate(
        {
            "content": "A cited answer.",
            "explainability": [{"references": ["context-1"]}],
            "context": [
                {
                    "id": "context-1",
                    "content": "Quoted evidence.",
                    "origins": [],
                }
            ],
        }
    )

    assert extract_subject("I was thinking about Klarna and how it grew.") == "Klarna"
    assert join_evidence(result)[0].carried_answer is True


def test_cited_page_lead_image_prefers_open_graph_and_resolves_relative_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("glia.discovery.fetch._reject_private_addresses", lambda _host: None)
    document = TextDocument(
        final_url="https://publisher.example/stories/klarna",
        body=(
            '<meta name="twitter:image" content="/twitter.jpg">'
            '<meta property="og:image" content="/lead.jpg">'
            '<img src="/inline.jpg">'
        ),
    )

    assert extract_lead_image(document) == "https://publisher.example/lead.jpg"


def test_visual_entity_query_reuses_the_cited_search_for_related_references() -> None:
    query = visual_entity_query("cobalt brutalism")

    assert "companies, products, works of art" in query
    assert "cobalt brutalism" in query
    assert "authoritative sources" in query


def test_visual_entity_is_only_attached_when_the_citation_names_it() -> None:
    result = CalaSearchResult.model_validate(
        {
            "content": "Braun and GDPR.",
            "explainability": [{"references": ["context-1"]}],
            "context": [
                {
                    "id": "context-1",
                    "content": "Braun established a restrained industrial design language.",
                    "origins": [
                        {
                            "source": {"name": "Design Museum"},
                            "document": {
                                "name": "Braun design history",
                                "url": "https://publisher.example/braun",
                            },
                        }
                    ],
                }
            ],
            "entities": [
                {"id": "braun", "name": "Braun", "entity_type": "Company"},
                {"id": "gdpr", "name": "GDPR", "entity_type": "Law"},
            ],
        }
    )
    evidence = join_evidence(result)[0]
    entity = visual_entity_for(evidence, evidence.origins[0], result.entities)

    assert entity is not None
    assert entity.name == "Braun"
