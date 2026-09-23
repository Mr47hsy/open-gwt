"""``MatchStore``: the only place live match state lives. Stores the canonical dict form so the
memory and the Redis implementation behave identically."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol


class VersionConflict(Exception):
    pass


class MatchStore(Protocol):
    async def load(self, match_id: str) -> tuple[dict[str, Any], int] | None: ...

    async def save(self, match_id: str, data: dict[str, Any], version: int) -> int: ...

    async def delete(self, match_id: str) -> None: ...

    def lock(self, match_id: str) -> AbstractAsyncContextManager[None]: ...


class MemoryMatchStore:
    def __init__(self) -> None:
        self._data: dict[str, tuple[dict[str, Any], int]] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def load(self, match_id: str) -> tuple[dict[str, Any], int] | None:
        return self._data.get(match_id)

    async def save(self, match_id: str, data: dict[str, Any], version: int) -> int:
        """Save when ``version`` is the current version; returns the new version."""
        current = self._data.get(match_id)
        current_version = current[1] if current is not None else 0
        if version != current_version:
            raise VersionConflict(f"{match_id}: expected version {current_version}, got {version}")
        self._data[match_id] = (data, version + 1)
        return version + 1

    async def delete(self, match_id: str) -> None:
        self._data.pop(match_id, None)
        self._locks.pop(match_id, None)

    @asynccontextmanager
    async def lock(self, match_id: str) -> AsyncIterator[None]:
        async with self._locks[match_id]:
            yield
