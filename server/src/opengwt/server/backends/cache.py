"""``Cache``: small, optional, TTL'd key-value storage."""

from __future__ import annotations

import time
from typing import Any, Protocol


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None: ...

    async def delete(self, key: str) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[Any, float | None]] = {}

    async def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if item is None:
            return None
        value, expires = item
        if expires is not None and expires <= time.monotonic():
            del self._items[key]
            return None
        return value

    async def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        expires = time.monotonic() + ttl_seconds if ttl_seconds is not None else None
        self._items[key] = (value, expires)

    async def delete(self, key: str) -> None:
        self._items.pop(key, None)
