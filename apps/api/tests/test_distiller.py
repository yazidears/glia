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
                    "visual_direction": [
                        {
                            "subject": "observatori brutalista",
                            "mood": ["solitari", "fred"],
                            "style": ["cinematic", "brutalist"],
                            "palette": ["blau cobalt"],
                            "composition": "pla general simetric",
                            "medium": "film still",
                            "era": "retrofuturisme dels anys 70",
                        }
                    ]
                },
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
