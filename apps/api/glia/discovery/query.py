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
        "color",
        "colour",
        "image",
        "images",
        "headquarters",
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

# Wikimedia and Openverse rank English search terms much more reliably than
# short translated nouns. Keep this deliberately small and exact: these are
# known demo subjects, not a general-purpose translation layer. Matching the
# complete cleaned subject means names and longer phrases stay untouched.
_SUBJECT_ALIASES: dict[tuple[str, ...], tuple[str, ...]] = {
    ("coches",): ("cars",),
    ("cotxes",): ("cars",),
    ("voitures",): ("cars",),
    ("gatos",): ("cats",),
    ("gats",): ("cats",),
    ("chats",): ("cats",),
    ("perros",): ("dogs",),
    ("gossos",): ("dogs",),
    ("chiens",): ("dogs",),
    ("gatos", "perros"): ("cats", "dogs"),
    ("gats", "gossos"): ("cats", "dogs"),
    ("chats", "chiens"): ("cats", "dogs"),
    ("manzanas", "verdes"): ("green", "apples"),
    ("pomes", "verdes"): ("green", "apples"),
    ("pommes", "vertes"): ("green", "apples"),
    ("avioneta", "militar"): ("military", "aircraft"),
    ("avioneta", "militars"): ("military", "aircraft"),
    ("avioneta", "militares"): ("military", "aircraft"),
}

_PALETTE_ALIASES = {
    "azul": "blue",
    "blau": "blue",
    "bleu": "blue",
    "verde": "green",
    "verd": "green",
    "vert": "green",
}

# Preview discovery runs while the user is still speaking, before the OpenAI
# query planner has translated the idea into corpus-friendly concepts. Keep it
# deliberately closed: an exact phrase that is not listed here gets no preview
# search, so the board keeps its current references instead of flashing an
# unrelated result for a literal speech fragment.
_MINIMAL_OUTLET_QUERIES = (
    "minimalist electrical outlet",
    "modern wall socket",
    "electrical outlet product design",
)
_OUTLET_QUERIES = (
    "electrical outlet",
    "wall socket",
)
_PREVIEW_QUERY_LADDERS: dict[tuple[str, ...], tuple[str, ...]] = {
    ("enchufe",): _OUTLET_QUERIES,
    ("enchufes",): _OUTLET_QUERIES,
    ("endoll",): _OUTLET_QUERIES,
    ("endolls",): _OUTLET_QUERIES,
    ("electrical", "outlet"): _OUTLET_QUERIES,
    ("electrical", "outlets"): _OUTLET_QUERIES,
    ("wall", "socket"): _OUTLET_QUERIES,
    ("wall", "sockets"): _OUTLET_QUERIES,
    ("enchufe", "minimalista"): _MINIMAL_OUTLET_QUERIES,
    ("enchufes", "minimalistas"): _MINIMAL_OUTLET_QUERIES,
    ("endoll", "minimalista"): _MINIMAL_OUTLET_QUERIES,
    ("endolls", "minimalistes"): _MINIMAL_OUTLET_QUERIES,
    ("minimalist", "electrical", "outlet"): _MINIMAL_OUTLET_QUERIES,
    ("minimalist", "electrical", "outlets"): _MINIMAL_OUTLET_QUERIES,
    ("minimalist", "wall", "socket"): _MINIMAL_OUTLET_QUERIES,
    ("minimalist", "wall", "sockets"): _MINIMAL_OUTLET_QUERIES,
}
_OUTLET_SUBJECTS = frozenset(
    {
        ("enchufe",),
        ("enchufes",),
        ("endoll",),
        ("endolls",),
        ("electrical", "outlet"),
        ("electrical", "outlets"),
        ("wall", "socket"),
        ("wall", "sockets"),
    }
)
_MINIMAL_STYLE_WORDS = frozenset(
    {"minimal", "minimalist", "minimalista", "minimalistas", "minimalistes"}
)


def build_queries(intent: VisualIntent) -> tuple[str, ...]:
    """Return the query ladder for one intent, sharpest first, possibly empty."""
    words = _search_subject_words(intent.subject)
    if not words:
        return ()

    # Spoken subjects are head-final — "a cold brutalist observatory" is about
    # the observatory — so the core keeps the last words and each broader rung
    # drops one more from the left.
    core = words[-MAX_SUBJECT_WORDS:]
    ladder: list[str] = []
    palette = _palette_sharpener(intent, taken=set(core))
    sharpeners = _sharpeners(intent, taken=set(core))
    if len(core) < MAX_SUBJECT_WORDS:
        if palette:
            # Colour is an adjective in the search corpora: "blue cars" is
            # materially less ambiguous than either "cars blue" or "coches".
            ladder.append(" ".join([palette, *core]))
        elif sharpeners:
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


def build_preview_queries(intent: VisualIntent) -> tuple[str, ...]:
    """Return fast, known-safe searches for an in-progress speech preview.

    Stable discovery has an OpenAI-planned query path and continues to use the
    general :func:`build_queries` ladder. This preview path intentionally emits
    nothing for unknown or project-level compounds; holding the existing board
    is more useful than searching a literal partial sentence.
    """
    subject = tuple(_words(intent.subject))
    if subject in _OUTLET_SUBJECTS and _has_minimal_style(intent):
        return _MINIMAL_OUTLET_QUERIES

    known_ladder = _PREVIEW_QUERY_LADDERS.get(subject)
    if known_ladder is not None:
        return known_ladder

    # Existing aliases are a small, exact list of measured live-demo concepts
    # whose English search terms are known to be useful in the open corpora.
    if subject in _SUBJECT_ALIASES:
        return build_queries(intent)
    return ()


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


def _palette_sharpener(intent: VisualIntent, *, taken: set[str]) -> str | None:
    for term in intent.palette:
        words = _words(term)
        if not words:
            continue
        colour = _PALETTE_ALIASES.get(words[0], words[0])
        if colour not in taken:
            return colour
    return None


def _has_minimal_style(intent: VisualIntent) -> bool:
    return any(
        word in _MINIMAL_STYLE_WORDS
        for term in [*intent.styles, *intent.moods]
        for word in _words(term)
    )


def _search_subject_words(value: str) -> list[str]:
    words = _words(value)
    return list(_SUBJECT_ALIASES.get(tuple(words), tuple(words)))


def _words(value: str) -> list[str]:
    cleaned = [word.strip(".,!?;:()[]{}\"'").lower() for word in value.split()]
    words = [word for word in cleaned if len(word) > 2 and word not in _NOISE and word.isalpha()]
    # Realtime speech providers occasionally repeat the last stable token while reconciling
    # deltas ("gatos gatos perros"). Searching the repeated form is slower and less relevant.
    return list(dict.fromkeys(words))
