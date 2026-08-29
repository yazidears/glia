import json

import httpx
import pytest

from glia.contracts import VisualIntent
from glia.realtime.distiller import DiscoveryGate, PioneerIntentDistiller


@pytest.mark.asyncio
async def test_pioneer_distiller_uses_native_private_inference_contract() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        assert request.url == "https://api.pioneer.ai/inference"
        assert request.headers["X-API-Key"] == "test-key"
        assert payload["model_id"] == "job-glia-visual-direction"
        assert payload["store"] is False
        fields = payload["schema"]["structures"]["visual_direction"]["fields"]
        assert [field["name"] for field in fields] == [
            "subject",
            "mood",
            "style",
            "palette",
            "composition",
            "medium",
            "era",
        ]
        return httpx.Response(
            200,
            json={
                "type": "encoder",
                "inference_id": "inference-fixture",
                "result": {
                    "request_id": None,
                    "created_at": 1_788_008_749,
                    "data": {
                        "visual_direction": [
                            {
                                "subject": {
                                    "text": "observatori brutalista",
                                    "confidence": 0.91,
                                },
                                "mood": [
                                    {"text": "solitari", "confidence": 0.83},
                                    {"text": "fred", "confidence": 0.79},
                                ],
                                "style": {
                                    "text": "cinematic",
                                    "confidence": 0.88,
                                },
                                "palette": {
                                    "text": "blau cobalt",
                                    "confidence": 0.86,
                                },
                                "composition": {
                                    "text": "pla general simetric",
                                    "confidence": 0.82,
                                },
                                "medium": {
                                    "text": "film still",
                                    "confidence": 0.94,
                                },
                                "era": None,
                            }
                        ],
                        "entities": {
                            "person": [],
                            "organization": [],
                            "location": [],
                            "product": [],
                            "work_of_art": [],
                        },
                    },
                },
                "model_id": "job-glia-visual-direction",
                "latency_ms": 231.8,
                "token_usage": 151,
                "model_used": "job-glia-visual-direction",
            },
        )

    distiller = PioneerIntentDistiller(
        api_key="test-key",
        base_url="https://api.pioneer.ai/v1",
        model="job-glia-visual-direction",
        timeout_seconds=1,
        max_retries=0,
        threshold=0.5,
        transport=httpx.MockTransport(handler),
    )

    first = await distiller.distill("Un observatori brutalista solitari de color blau cobalt")
    second = await distiller.distill("Un observatori brutalista solitari de color blau cobalt")

    assert calls == 1
    assert first == second
    assert first.source == "pioneer"
    assert first.intent.medium == "film still"
    assert first.intent.palette == ["blau cobalt"]
    assert first.intent.moods == ["fred", "solitari"]
    assert first.intent.era == ""


def test_discovery_gate_only_moves_baseline_when_visual_direction_changes() -> None:
    gate = DiscoveryGate(jaccard_threshold=0.4)
    initial = VisualIntent(
        subject="observatory",
        moods=["cold"],
        styles=["brutalist"],
        palette=["cobalt"],
        medium="film still",
        era="1970s",
    )

    assert gate.evaluate(initial).reasons == ["initial"]
    assert not gate.evaluate(initial).should_discover

    changed = initial.model_copy(update={"moods": ["warm"], "palette": ["amber"]})
    decision = gate.evaluate(changed)

    assert decision.should_discover
    assert decision.reasons == ["visual_attributes"]
