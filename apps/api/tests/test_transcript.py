from glia.realtime.transcript import FastIntentProjector, TranscriptAccumulator


def test_accumulator_orders_items_by_first_seen_and_replaces_partial_with_final() -> None:
    transcript = TranscriptAccumulator()

    assert transcript.append_delta("event-1", "item-1", "A cold ")
    assert transcript.append_delta("event-2", "item-2", "blue room")
    assert transcript.complete("event-3", "item-1", "A cold cinematic room")

    assert transcript.snapshot() == "A cold cinematic room blue room"


def test_accumulator_ignores_duplicate_events() -> None:
    transcript = TranscriptAccumulator()

    assert transcript.append_delta("event-1", "item-1", "warm")
    assert not transcript.append_delta("event-1", "item-1", "warm")
    assert transcript.snapshot() == "warm"


def test_fast_projector_returns_useful_visual_attributes_without_network() -> None:
    intent = FastIntentProjector().project(
        "A lonely brutalist observatory in cobalt blue, cinematic and cold"
    )

    assert intent.subject == "observatory"
    assert intent.moods == ["cold", "lonely"]
    assert intent.styles == ["brutalist", "cinematic"]
    assert intent.palette == ["blue", "cobalt"]
