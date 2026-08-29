"""Whether a distilled subject is worth spending a query on.

The transcript "Hola, hola, hola, por qué va tan lento" distilled to a subject that
resolved against Cala to the UK company WHY WHY LIMITED, and the same words went to
both image lanes. Nobody was talking about a company. Filler is what a person says
while thinking, and a distiller handed filler returns filler with a straight face —
so the refusal has to live here, in front of every query, rather than in each caller.

Three independent reasons to refuse, all cheap and all local: too short to be a
subject, a known filler word in any of the languages this app transcribes, or the
distiller itself saying it was guessing.
"""

from dataclasses import dataclass

MIN_SUBJECT_CHARACTERS = 4

#: Filler across the four transcription languages plus the English the model leaks.
#: Only whole-subject matches are refused — "vale" alone is filler, "vale de bravo"
#: is a place — so this is checked against every word, not as a substring.
STOPWORDS = frozenset(
    {
        # English
        "and",
        "but",
        "erm",
        "hey",
        "huh",
        "like",
        "mmm",
        "okay",
        "right",
        "sure",
        "ok",
        "that",
        "the",
        "then",
        "there",
        "this",
        "uhh",
        "umm",
        "well",
        "what",
        "when",
        "where",
        "which",
        "why",
        "yeah",
        "yep",
        "yes",
        "you",
        "know",
        "mean",
        "sorry",
        "just",
        "really",
        "very",
        "some",
        "thing",
        "stuff",
        "anyway",
        "actually",
        # Spanish
        "hola",
        "vale",
        "bueno",
        "pues",
        "claro",
        "entonces",
        "porque",
        "por",
        "que",
        "qué",
        "como",
        "cómo",
        "esto",
        "eso",
        "esta",
        "nada",
        "bien",
        "oye",
        "venga",
        "tío",
        "tia",
        "tía",
        "gracias",
        "perdón",
        "mira",
        "sea",
        "para",
        # Catalan
        "doncs",
        "vinga",
        "escolta",
        "això",
        "aixo",
        "bé",
        "be",
        "perquè",
        "perque",
        "gràcies",
        "gracies",
        "adéu",
        "adeu",
        # French
        "bonjour",
        "salut",
        "alors",
        "donc",
        "voilà",
        "voila",
        "bah",
        "ben",
        "quoi",
        "enfin",
        "merci",
        "euh",
        "hein",
        "ouais",
        "bon",
    }
)


@dataclass(frozen=True)
class SubjectRefusal:
    """Why a subject was refused. `reason` is a log key, not a user-facing string."""

    reason: str
    detail: str


def refuse_subject(
    subject: str | None, *, confidence: float | None = None, min_confidence: float = 0.0
) -> SubjectRefusal | None:
    """Return why this subject must not be queried, or None to let it through.

    `confidence` is the distiller's own score for the subject field when it reported
    one. A distiller that does not score its output (the local projector, the fixture)
    passes None, and an absent score is never treated as a low one — this guard refuses
    what it can prove is noise, not everything it cannot vouch for.
    """
    if subject is None:
        return SubjectRefusal("missing", "The distiller returned no subject.")

    cleaned = " ".join(subject.split())
    if len(cleaned) < MIN_SUBJECT_CHARACTERS:
        return SubjectRefusal(
            "too_short", f"Subject is shorter than {MIN_SUBJECT_CHARACTERS} characters."
        )

    words = [word.strip(".,!?;:()[]{}\"'¿¡").lower() for word in cleaned.split()]
    words = [word for word in words if word]
    if not words:
        return SubjectRefusal("no_words", "Subject has no word characters.")
    # A word carries the subject only if it is neither filler nor too short to name
    # anything. "hola hola" has no such word; "por qué" has none either.
    if not [word for word in words if word not in STOPWORDS and len(word) >= 3]:
        return SubjectRefusal("stopword", "Subject is filler with no content word.")

    if confidence is not None and confidence < min_confidence:
        return SubjectRefusal(
            "low_confidence",
            f"Distiller confidence {confidence:.2f} is below {min_confidence:.2f}.",
        )
    return None
