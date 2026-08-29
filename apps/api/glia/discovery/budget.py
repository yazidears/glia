"""Budget controls for the single Cala call site.

Credits are the only scarce resource in this system (docs/STACK.md § "Cost model"): the pool
is monthly, 1 credit = 1 query, and a leaking loop drains it in seconds. Three controls live
here — a per-session debounce, a TTL cache, and a ledger with a hard stop — and the Cala client
may not issue a request without passing all three.

In-process on purpose. Redis is the eventual home; today the process is single and the swap is
one interface later. The consequence is honest and worth stating: restarting the API resets
both the cache and the ledger.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field


def cache_key(text: str) -> str:
    """Hash of the normalised query. Case and whitespace differences are the same question."""
    normalised = " ".join(text.split()).casefold()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


@dataclass
class _Entry[T]:
    value: T
    expires_at: float


class TtlCache[T]:
    """A tiny TTL dict. Holds the raw upstream payload so the source panel renders from cache
    with the same fidelity as a live answer — a cache hit must be indistinguishable on screen."""

    def __init__(self, ttl_seconds: float, max_entries: int = 512) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[str, _Entry[T]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> T | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._entries[key]
                return None
            return entry.value

    def set(self, key: str, value: T) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._entries) >= self._max_entries:
                self._evict_locked(now)
            self._entries[key] = _Entry(value=value, expires_at=now + self._ttl)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _evict_locked(self, now: float) -> None:
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            del self._entries[key]
        if len(self._entries) < self._max_entries:
            return
        oldest = min(self._entries, key=lambda key: self._entries[key].expires_at)
        del self._entries[oldest]


class BudgetExhausted(Exception):
    """Raised instead of spending a credit we do not have."""


@dataclass
class CreditLedger:
    """A process counter of credits spent, and the hard stop that makes it binding.

    `entity_calls` is tracked apart from `search_calls` because docs/PARTNERS.md records it as
    undocumented whether `GET /entities` consumes a credit. Both are charged against the budget
    — overcounting costs us headroom, undercounting costs us the demo — and keeping them
    separate is what makes the real cost measurable against the console meter.
    """

    budget: int
    search_calls: int = 0
    entity_calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def spent(self) -> int:
        return self.search_calls + self.entity_calls

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.spent)

    def reserve(self, kind: str) -> None:
        """Charge one credit up front, or refuse. Charging before the call rather than after
        means a request that times out mid-flight is still counted: Cala bills the query, not
        our ability to read the response."""
        with self._lock:
            if self.spent >= self.budget:
                raise BudgetExhausted(
                    f"Cala credit budget of {self.budget} is exhausted; refusing to query."
                )
            if kind == "entities":
                self.entity_calls += 1
            else:
                self.search_calls += 1


class SessionDebounce:
    """Minimum seconds of new settled speech between queries, enforced per session.

    A request inside the window is not an error and not a new query: it replays the last result
    for that session. The client guards too, but the client is not the one holding the budget.
    """

    def __init__(self, min_seconds: float) -> None:
        self._min_seconds = min_seconds
        self._last_query_at: dict[str, float] = {}
        self._lock = threading.Lock()

    def seconds_remaining(self, session_id: str) -> float:
        with self._lock:
            last = self._last_query_at.get(session_id)
        if last is None:
            return 0.0
        return max(0.0, self._min_seconds - (time.monotonic() - last))

    def mark(self, session_id: str) -> None:
        with self._lock:
            self._last_query_at[session_id] = time.monotonic()

    def clear(self) -> None:
        with self._lock:
            self._last_query_at.clear()
