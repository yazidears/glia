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
    _stopwords: ClassVar[set[str]] = {
        "about",
        "actually",
        "and",
        "but",
        "for",
        "from",
        "have",
        "image",
        "like",
        "more",
        "something",
        "that",
        "the",
        "this",
        "want",
        "with",
    }

    def project(self, transcript: str) -> VisualIntent:
        words = [word.strip(".,!?;:()[]{}\"'").lower() for word in transcript.split()]
        meaningful = [
            word
            for word in words
            if len(word) > 2
            and word not in self._stopwords
            and word not in self._moods
            and word not in self._styles
            and word not in self._palette
            and word.isalpha()
        ]
        subject = " ".join(meaningful[-6:]) if meaningful else transcript.strip()[-80:]
        return VisualIntent(
            subject=subject,
            moods=self._matches(words, self._moods),
            styles=self._matches(words, self._styles),
            palette=self._matches(words, self._palette),
        )

    @staticmethod
    def _matches(words: list[str], vocabulary: set[str]) -> list[str]:
        return sorted(set(words).intersection(vocabulary))
