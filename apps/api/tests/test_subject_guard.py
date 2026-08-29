"""No subject, no query.

The incident these tests encode: the transcript "Hola, hola, hola, por qué va tan
lento" distilled to a subject that Cala resolved to the UK company WHY WHY LIMITED,
and the same words were handed to both image lanes. Every case below is a query that
must never leave the process.
"""

import pytest

from glia.discovery.subject import MIN_SUBJECT_CHARACTERS, refuse_subject


@pytest.mark.parametrize(
    "subject",
    ["a brutalist observatory at dusk", "observatory", "salt flats", "Runder Turm"],
)
def test_a_real_subject_is_allowed(subject: str) -> None:
    assert refuse_subject(subject) is None


def test_a_missing_subject_is_refused() -> None:
    refusal = refuse_subject(None)
    assert refusal is not None
    assert refusal.reason == "missing"


@pytest.mark.parametrize("subject", ["", "  ", "ok", "why", "a", "no"])
def test_a_subject_under_the_minimum_length_is_refused(subject: str) -> None:
    refusal = refuse_subject(subject)
    assert refusal is not None
    assert refusal.reason in {"too_short", "missing"}
    assert len(subject.strip()) < MIN_SUBJECT_CHARACTERS


@pytest.mark.parametrize(
    "subject",
    [
        "hola hola",
        "hola, hola, hola",
        "por qué",
        "vale tío",
        "yeah okay",
        "bueno pues",
        "what is this",
        "doncs vinga",
        "alors bon",
    ],
)
def test_filler_in_every_language_is_refused(subject: str) -> None:
    refusal = refuse_subject(subject)
    assert refusal is not None
    assert refusal.reason == "stopword"


def test_filler_around_one_real_word_still_queries() -> None:
    """The guard refuses noise, not every sentence containing a filler word."""
    assert refuse_subject("bueno, el observatorio") is None


def test_low_distiller_confidence_is_refused() -> None:
    refusal = refuse_subject("brutalist observatory", confidence=0.1, min_confidence=0.3)
    assert refusal is not None
    assert refusal.reason == "low_confidence"


def test_confident_enough_passes() -> None:
    assert refuse_subject("brutalist observatory", confidence=0.9, min_confidence=0.3) is None


def test_an_unscored_distiller_is_not_treated_as_a_low_score() -> None:
    """The local projector and the fixture report no confidence. Absent is not low."""
    assert refuse_subject("brutalist observatory", confidence=None, min_confidence=0.9) is None
