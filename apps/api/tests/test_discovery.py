"""Tests for the Cala call site.

The budget controls are the point of these tests. A leaking loop is the worst outcome of this
integration, so the debounce, the cache and the ledger each get a test that fails if a credit
is spent when it should not be.
"""

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from glia.api import get_cala_client
from glia.config import Settings
from glia.contracts import CalaSearchResult
from glia.discovery.budget import BudgetExhausted, CreditLedger, SessionDebounce, cache_key
from glia.discovery.cala import CalaClient, CalaRateLimited, extract_subject, join_evidence
from glia.main import create_app

SEARCH_BODY: dict[str, Any] = {
    "content": "Klarna is a Swedish payments company.",
    "explainability": [
        {"content": "Klarna was founded in Stockholm in 2005.", "references": ["knowbit-1"]}
    ],
    "context": [
        {
            "id": "knowbit-1",
            "content": "Klarna was founded in Stockholm in 2005.",
            "origins": [
                {
                    "source": {"name": "Impact Loop", "url": "https://www.impactloop.com/"},
                    "document": {
                        "name": "Inside Klarna",
                        "url": "https://www.impactloop.com/artikel/klarna",
                    },
                }
            ],
        },
        {"id": "knowbit-2", "content": "Unreferenced background.", "origins": []},
    ],
    "entities": [{"id": "e-1", "name": "Klarna", "entity_type": "Company", "mentions": ["Klarna"]}],
}

ENTITY_BODY: list[dict[str, Any]] = [
    {
        "id": "e-1",
        "name": "Klarna",
        "entity_type": "Company",
        "description": "A Swedish payments company.",
    }
]


def settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "cala_api_key": "test-key-not-a-real-credential",
        "cala_base_url": "https://cala.test/v1",
        "cala_min_seconds_between_queries": 0.0,
        "cala_credit_budget": 50,
    }
    base.update(overrides)
    return Settings(**base)


class _Recorder:
    """Stands in for Cala. Counts requests so a test can assert nothing was spent."""

    def __init__(self, status: int = 200) -> None:
        self.requests: list[httpx.Request] = []
        self.status = status

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "rate_limit_exceeded"})
        if request.url.path.endswith("/entities"):
            return httpx.Response(200, json=ENTITY_BODY)
        return httpx.Response(200, json=SEARCH_BODY)


def stub(client: CalaClient, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(recorder.handler)
    original = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(**kwargs)

    monkeypatch.setattr("glia.discovery.cala.httpx.AsyncClient", factory)


# ─── subject heuristic ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("I was thinking about Klarna and how they grew.", "Klarna"),
        ("The Bauhaus school in Weimar", "Bauhaus"),
        ("something quiet and blue", "quiet blue"),
        ("", None),
    ],
)
def test_extract_subject(transcript: str, expected: str | None) -> None:
    assert extract_subject(transcript) == expected


def test_extract_subject_ignores_sentence_opening_filler() -> None:
    # "The" opens the sentence and is a stopword, so it must not become the subject.
    assert extract_subject("The company is called Monzo.") == "Monzo"


# ─── explainability join ────────────────────────────────────────────────────────


def test_join_evidence_marks_and_orders_cited_items() -> None:
    items = join_evidence(CalaSearchResult.model_validate(SEARCH_BODY))
    assert [item.id for item in items] == ["knowbit-1", "knowbit-2"]
    assert items[0].carried_answer is True
    assert items[1].carried_answer is False


def test_join_evidence_keeps_publisher_and_document_urls() -> None:
    origin = join_evidence(CalaSearchResult.model_validate(SEARCH_BODY))[0].origins[0]
    assert origin.source is not None and origin.source.name == "Impact Loop"
    assert origin.document is not None
    assert origin.document.url == "https://www.impactloop.com/artikel/klarna"


def test_search_parser_invents_no_image_field() -> None:
    # Cala returns no images. If a field like this ever appears here it is a bug, not a feature.
    assert not {"image", "image_url", "thumbnail", "logo", "media"} & set(
        CalaSearchResult.model_fields
    )


# ─── budget controls ────────────────────────────────────────────────────────────


def test_ledger_counts_entity_calls_separately_and_stops_at_budget() -> None:
    ledger = CreditLedger(budget=2)
    ledger.reserve("entities")
    ledger.reserve("search")
    assert (ledger.entity_calls, ledger.search_calls, ledger.remaining) == (1, 1, 0)
    with pytest.raises(BudgetExhausted):
        ledger.reserve("search")


def test_debounce_blocks_then_releases() -> None:
    debounce = SessionDebounce(min_seconds=60.0)
    assert debounce.seconds_remaining("s-1") == 0.0
    debounce.mark("s-1")
    assert debounce.seconds_remaining("s-1") > 0
    assert debounce.seconds_remaining("s-2") == 0.0


def test_cache_key_normalises_whitespace_and_case() -> None:
    assert cache_key("  Klarna   Payments ") == cache_key("klarna payments")


@pytest.mark.asyncio
async def test_repeated_search_costs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CalaClient(settings())
    recorder = _Recorder()
    stub(client, recorder, monkeypatch)

    first, first_cached = await client.search("Klarna")
    second, second_cached = await client.search("  klarna  ")

    assert (first_cached, second_cached) == (False, True)
    assert first.content == second.content
    assert len(recorder.requests) == 1
    assert client.ledger.search_calls == 1


@pytest.mark.asyncio
async def test_auth_header_is_x_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CalaClient(settings())
    recorder = _Recorder()
    stub(client, recorder, monkeypatch)

    await client.search("Klarna")

    request = recorder.requests[0]
    assert request.headers["X-API-KEY"] == "test-key-not-a-real-credential"
    assert "authorization" not in request.headers


@pytest.mark.asyncio
async def test_rate_limit_is_typed_and_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CalaClient(settings())
    recorder = _Recorder(status=429)
    stub(client, recorder, monkeypatch)

    with pytest.raises(CalaRateLimited):
        await client.search("Klarna")

    # Retrying a rate limit only spends the budget faster.
    assert len(recorder.requests) == 1


# ─── the route ──────────────────────────────────────────────────────────────────


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Any:
    get_cala_client.cache_clear()
    client = CalaClient(settings())
    recorder = _Recorder()
    stub(client, recorder, monkeypatch)
    app = create_app()
    app.dependency_overrides[get_cala_client] = lambda: client
    with TestClient(app) as http:
        yield http, client, recorder
    get_cala_client.cache_clear()


def test_discover_returns_entity_answer_and_cited_evidence(api: Any) -> None:
    http, _client, _recorder = api
    body = http.post(
        "/v1/discover", json={"transcript": "Tell me about Klarna.", "session_id": "s-1"}
    ).json()

    assert body["status"] == "ok"
    assert body["entity"]["name"] == "Klarna"
    assert body["entity"]["entity_type"] == "Company"
    assert body["answer"].startswith("Klarna is")
    assert body["context"][0]["carried_answer"] is True
    assert body["ledger"]["entity_calls"] == 1
    assert body["ledger"]["search_calls"] == 1


def test_second_turn_inside_the_window_spends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    get_cala_client.cache_clear()
    client = CalaClient(settings(cala_min_seconds_between_queries=60.0))
    recorder = _Recorder()
    stub(client, recorder, monkeypatch)
    app = create_app()
    app.dependency_overrides[get_cala_client] = lambda: client
    with TestClient(app) as http:
        payload = {"transcript": "Tell me about Klarna.", "session_id": "s-1"}
        http.post("/v1/discover", json=payload)
        spent_after_first = client.ledger.spent
        second = http.post("/v1/discover", json=payload).json()

    assert second["cached"] is True
    assert second["status"] == "ok"
    assert client.ledger.spent == spent_after_first
    get_cala_client.cache_clear()


def test_exhausted_budget_refuses_without_calling(monkeypatch: pytest.MonkeyPatch) -> None:
    get_cala_client.cache_clear()
    client = CalaClient(settings(cala_credit_budget=0))
    recorder = _Recorder()
    stub(client, recorder, monkeypatch)
    app = create_app()
    app.dependency_overrides[get_cala_client] = lambda: client
    with TestClient(app) as http:
        body = http.post(
            "/v1/discover", json={"transcript": "Tell me about Klarna.", "session_id": "s-1"}
        ).json()

    assert body["status"] == "budget_exhausted"
    assert recorder.requests == []
    get_cala_client.cache_clear()


def test_missing_key_is_a_problem_document_not_a_stack_trace() -> None:
    get_cala_client.cache_clear()
    client = CalaClient(Settings(cala_api_key=None))
    app = create_app()
    app.dependency_overrides[get_cala_client] = lambda: client
    with TestClient(app) as http:
        response = http.post(
            "/v1/discover", json={"transcript": "Tell me about Klarna.", "session_id": "s-1"}
        )

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "cala_not_configured"
    assert "correlation_id" in body
    assert "traceback" not in response.text.lower()
    get_cala_client.cache_clear()


def test_ledger_endpoint_reports_spend(api: Any) -> None:
    http, _client, _recorder = api
    http.post("/v1/discover", json={"transcript": "Tell me about Klarna.", "session_id": "s-1"})
    body = http.get("/v1/ledger").json()
    assert body["spent"] == body["search_calls"] + body["entity_calls"]
    assert body["remaining"] == body["budget"] - body["spent"]
