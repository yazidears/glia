"""Turn a distilled visual intent into search queries for the open corpora.

Both corpora AND their terms, so a long query reliably returns nothing:
measured today, "brutalist observatory cinematic" returns zero results on
Commons and zero on Openverse, "brutalist observatory" returns two and five,
and "observatory" returns twenty and twenty. So this builds a ladder — the
sharpest query first, progressively broader ones behind it — and a lane walks
down it until it has enough to fill a wave.
"""

from glia.contracts import VisualIntent

MAX_SUBJECT_WORDS = 3
MAX_SHARPENERS = 1
MAX_CHARACTERS = 80
MAX_RUNGS = 3

_NOISE = frozenset(
    {
        "image",
        "images",
        "kind",
        "photo",
        "photos",
        "picture",
        "pictures",
        "something",
        "sort",
        "thing",
        "things",
    }
)


def build_queries(intent: VisualIntent) -> tuple[str, ...]:
    """Return the query ladder for one intent, sharpest first, possibly empty."""
    words = _words(intent.subject)
    if not words:
        return ()

    # Spoken subjects are head-final — "a cold brutalist observatory" is about
    # the observatory — so the core keeps the last words and each broader rung
    # drops one more from the left.
    core = words[-MAX_SUBJECT_WORDS:]
    ladder: list[str] = []
    sharpeners = _sharpeners(intent, taken=set(core))
    if sharpeners and len(core) < MAX_SUBJECT_WORDS:
        ladder.append(" ".join([*core, *sharpeners]))
    for start in range(len(core)):
        ladder.append(" ".join(core[start:]))

    seen: set[str] = set()
    unique: list[str] = []
    for query in ladder:
        trimmed = query[:MAX_CHARACTERS].strip()
        if trimmed and trimmed not in seen:
            seen.add(trimmed)
            unique.append(trimmed)
    return tuple(unique[:MAX_RUNGS])


def subject_key(intent: VisualIntent) -> str:
    """The subject alone, as the identity of what the user is talking about.

    Discovery re-runs when this changes. A new mood or style sharpens the query
    but does not refill the grid — the subject is what materially moved.
    """
    return " ".join(_words(intent.subject)[-MAX_SUBJECT_WORDS:])


def _sharpeners(intent: VisualIntent, *, taken: set[str]) -> list[str]:
    sharpeners: list[str] = []
    for term in [*intent.styles, *intent.moods]:
        words = _words(term)
        if not words or len(sharpeners) >= MAX_SHARPENERS:
            continue
        head = words[0]
        if head in taken:
            continue
        taken.add(head)
        sharpeners.append(head)
    return sharpeners


def _words(value: str) -> list[str]:
    cleaned = [word.strip(".,!?;:()[]{}\"'").lower() for word in value.split()]
    return [word for word in cleaned if len(word) > 2 and word not in _NOISE and word.isalpha()]
