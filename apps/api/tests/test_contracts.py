import pytest
from pydantic import ValidationError

from glia.config import Settings
from glia.contracts import Candidate, CandidatesBatch, LedgerUpdated

VALID = {
    "id": "commons:1",
    "lane": "open",
    "image_url": "https://api.glia.test/api/image?url=https%3A%2F%2Fupload.wikimedia.org%2Fa.jpg",
    "source_url": "https://commons.wikimedia.org/wiki/File:A.jpg",
    "publisher": "Wikimedia Commons",
    "title": "A",
    "licence": "CC BY-SA 4.0",
    "width": 800,
    "height": 600,
    "score": 0.9,
}


def test_a_valid_batch_parses() -> None:
    batch = CandidatesBatch.model_validate({"revision": 2, "candidates": [VALID]})

    assert batch.type == "candidates.batch"
    assert batch.candidates[0].lane == "open"
    assert batch.candidates[0].evidence is None


def test_a_candidate_with_a_null_evidence_quote_parses() -> None:
    candidate = Candidate.model_validate({**VALID, "evidence": None})

    assert candidate.evidence is None
    assert candidate.entity_name is None


def test_an_unknown_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Candidate.model_validate({**VALID, "thumbnail": "https://upload.wikimedia.org/t.jpg"})


def test_an_unknown_lane_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Candidate.model_validate({**VALID, "lane": "generated"})


def test_the_ledger_message_carries_the_three_counters() -> None:
    ledger = LedgerUpdated(cala_queries=3, references=41, cited=12)

    assert ledger.model_dump() == {
        "type": "ledger.updated",
        "cala_queries": 3,
        "references": 41,
        "cited": 12,
    }


def test_the_api_refuses_to_start_on_an_unfilled_user_agent() -> None:
    """A `<org>` placeholder identifies nobody. Wikimedia's policy is what this guards."""
    with pytest.raises(ValidationError):
        Settings(image_fetch_user_agent="glia/0.1 (+https://github.com/<org>/glia)")


def test_an_empty_user_agent_is_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(image_fetch_user_agent="   ")


def test_a_real_contact_user_agent_is_accepted() -> None:
    settings = Settings(
        image_fetch_user_agent="glia/0.1 (+https://github.com/nectios/glia; glia@nectios.com)"
    )
    assert "<" not in settings.image_fetch_user_agent
