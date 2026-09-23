from __future__ import annotations

from opengwt.server.config import MEMORY_SCHEME, ConfigError

from .bus import EventBus, MemoryEventBus
from .cache import Cache, MemoryCache
from .store import MatchStore, MemoryMatchStore

_LATER = "the {kind} backend for {url!r} arrives with milestone M2b; use memory:// for now"


def make_match_store(url: str) -> MatchStore:
    if url.startswith(MEMORY_SCHEME):
        return MemoryMatchStore()
    raise ConfigError(_LATER.format(kind="match store", url=url))


def make_event_bus(url: str, history: int = 2000) -> EventBus:
    if url.startswith(MEMORY_SCHEME):
        return MemoryEventBus(history)
    raise ConfigError(_LATER.format(kind="event bus", url=url))


def make_cache(url: str) -> Cache:
    if url.startswith(MEMORY_SCHEME):
        return MemoryCache()
    raise ConfigError(_LATER.format(kind="cache", url=url))
