import re
from dataclasses import dataclass
from typing import ClassVar

from glia.contracts import VisualIntent


@dataclass
class TranscriptItem:
    order: int
    partial: str = ""
    final: str | None = None

    @property
    def text(self) -> str:
        return self.final if self.final is not None else self.partial


class TranscriptAccumulator:
    def __init__(self) -> None:
        self._items: dict[str, TranscriptItem] = {}
        self._seen_events: set[str] = set()
        self._next_order = 0

    def append_delta(self, event_id: str, item_id: str, delta: str) -> bool:
        if not self._mark_seen(event_id):
            return False
        item = self._item(item_id)
        if item.final is None:
            item.partial += delta
        return True

    def complete(self, event_id: str, item_id: str, transcript: str) -> bool:
        if not self._mark_seen(event_id):
            return False
        self._item(item_id).final = transcript.strip()
        return True

    def item_text(self, item_id: str) -> str:
        item = self._items.get(item_id)
        return "" if item is None else item.text

    def snapshot(self) -> str:
        ordered = sorted(self._items.values(), key=lambda item: item.order)
        return " ".join(item.text.strip() for item in ordered if item.text.strip())

    def _mark_seen(self, event_id: str) -> bool:
        if event_id in self._seen_events:
            return False
        self._seen_events.add(event_id)
        return True

    def _item(self, item_id: str) -> TranscriptItem:
        item = self._items.get(item_id)
        if item is None:
            item = TranscriptItem(order=self._next_order)
            self._items[item_id] = item
            self._next_order += 1
        return item


class FastIntentProjector:
    """A deterministic, zero-network projection used until Pioneer settles the turn."""

    _moods: ClassVar[set[str]] = {
        "calm",
        "cold",
        "dreamy",
        "hopeful",
        "lonely",
        "melancholic",
        "moody",
        "nostalgic",
        "playful",
        "quiet",
        "warm",
    }
    _styles: ClassVar[set[str]] = {
        "abstract",
        "brutalist",
        "cinematic",
        "editorial",
        "minimalist",
        "photographic",
        "surreal",
        "vintage",
    }
    _style_aliases: ClassVar[dict[str, str]] = {
        "cinematica": "cinematic",
        "cinemática": "cinematic",
        "minimalista": "minimalist",
        "surrealista": "surreal",
    }
    _ui_terms: ClassVar[dict[str, str]] = {
        "app": "app",
        "aplicacion": "app",
        "aplicación": "app",
        "branding": "branding",
        "club": "club",
        "clubs": "club",
        "dashboard": "dashboard",
        "diseno": "ui",
        "diseño": "ui",
        "entradas": "ticketing",
        "events": "events",
        "eventos": "events",
        "interfaz": "ui",
        "interface": "ui",
        "logo": "branding",
        "logos": "branding",
        "mockup": "mockup",
        "tickets": "ticketing",
        "ui": "ui",
        "web": "website",
        "website": "website",
    }
    _palette: ClassVar[set[str]] = {
        "amber",
        "black",
        "blue",
        "cobalt",
        "green",
        "grey",
        "orange",
        "pink",
        "red",
        "white",
        "yellow",
    }
    _palette_aliases: ClassVar[dict[str, str]] = {
        "amarillo": "yellow",
        "amarilla": "yellow",
        "azul": "blue",
        "azules": "blue",
        "blanc": "white",
        "blanca": "white",
        "blanco": "white",
        "blau": "blue",
        "blaus": "blue",
        "blaves": "blue",
        "gris": "grey",
        "groc": "yellow",
        "negra": "black",
        "negre": "black",
        "negro": "black",
        "roja": "red",
        "rojo": "red",
        "taronja": "orange",
        "verd": "green",
        "verde": "green",
        "vermell": "red",
    }
    _stopwords: ClassVar[set[str]] = {
        "aquesta",
        "aquest",
        "about",
        "actually",
        "and",
        "avec",
        "but",
        "con",
        "color",
        "de",
        "des",
        "donde",
        "els",
        "estoy",
        "faire",
        "for",
        "from",
        "hay",
        "have",
        "image",
        "idea",
        "las",
        "like",
        "los",
        "mais",
        "mes",
        "more",
        "més",
        "pour",
        "que",
        "quiero",
        "sobre",
        "son",
        "something",
        "that",
        "the",
        "this",
        "tengo",
        "una",
        "unas",
        "une",
        "unos",
        "uns",
        "want",
        "with",
        "vull",
        "where",
    }

    def project(self, transcript: str) -> VisualIntent:
        words = self._words(transcript)
        # The latest clause best represents the visual direction while someone is still
        # speaking. It prevents an earlier premise (for example "una empresa") from
        # displacing the concrete subject introduced immediately afterwards.
        clauses = [clause for clause in re.split(r"[.!?;]+", transcript) if clause.strip()]
        subject_words = self._words(clauses[-1]) if clauses else words
        meaningful = [
            word
            for word in subject_words
            if len(word) > 2
            and word not in self._stopwords
            and word not in self._moods
            and word not in self._styles
            and word not in self._style_aliases
            and word not in self._palette
            and word not in self._palette_aliases
            and word.isalpha()
        ]
        # Do not spend even a free open-corpus request on speech scaffolding such as "quiero
        # unas". An empty subject keeps the optimistic lane idle until a real noun or descriptor
        # arrives; once it does, partial speech can start returning photographs immediately.
        subject = self._ui_subject(words) or " ".join(dict.fromkeys(meaningful[-6:]))
        return VisualIntent(
            subject=subject,
            moods=self._matches(words, self._moods),
            styles=self._aliased_matches(words, self._styles, self._style_aliases),
            palette=self._palette_matches(words),
        )

    @staticmethod
    def _words(text: str) -> list[str]:
        return [word.strip(".,!?;:()[]{}\"'").lower() for word in text.split()]

    def _palette_matches(self, words: list[str]) -> list[str]:
        matches = set(words).intersection(self._palette)
        matches.update(
            self._palette_aliases[word] for word in words if word in self._palette_aliases
        )
        return sorted(matches)

    @classmethod
    def _ui_subject(cls, words: list[str]) -> str:
        """Anchor product conversation in a visual UI domain instead of its latest verb phrase."""
        present = {cls._ui_terms[word] for word in words if word in cls._ui_terms}
        if not present:
            return ""
        ordered = [
            term
            for term in (
                "club",
                "ticketing",
                "events",
                "dashboard",
                "app",
                "website",
                "mockup",
                "branding",
            )
            if term in present
        ]
        return " ".join(dict.fromkeys([*ordered[:2], "ui"]))

    @staticmethod
    def _aliased_matches(
        words: list[str], vocabulary: set[str], aliases: dict[str, str]
    ) -> list[str]:
        matches = set(words).intersection(vocabulary)
        matches.update(aliases[word] for word in words if word in aliases)
        return sorted(matches)

    @staticmethod
    def _matches(words: list[str], vocabulary: set[str]) -> list[str]:
        return sorted(set(words).intersection(vocabulary))
