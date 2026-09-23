"""``EventBus``: ordered per-match payloads with a short history for ``resync``."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from typing import Any, Protocol


class EventBus(Protocol):
    async def publish(self, match_id: str, seq: int, payload: dict[str, Any]) -> None: ...

    async def history(self, match_id: str, since_seq: int) -> list[dict[str, Any]]: ...

    def subscribe(self, match_id: str, since_seq: int) -> AsyncIterator[dict[str, Any]]: ...

    async def close(self, match_id: str) -> None: ...


class MemoryEventBus:
    def __init__(self, history: int = 2000) -> None:
        self._history_len = history
        self._history: dict[str, deque[tuple[int, dict[str, Any]]]] = {}
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any] | None]]] = {}

    async def publish(self, match_id: str, seq: int, payload: dict[str, Any]) -> None:
        payload = {**payload, "seq": seq}
        self._history.setdefault(match_id, deque(maxlen=self._history_len)).append((seq, payload))
        for queue in list(self._subscribers.get(match_id, [])):
            queue.put_nowait(payload)

    async def history(self, match_id: str, since_seq: int) -> list[dict[str, Any]]:
        return [p for s, p in self._history.get(match_id, ()) if s > since_seq]

    async def subscribe(self, match_id: str, since_seq: int) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._subscribers.setdefault(match_id, []).append(queue)
        try:
            last = since_seq
            for payload in await self.history(match_id, since_seq):
                last = payload["seq"]
                yield payload
            while True:
                item = await queue.get()
                if item is None:
                    return
                if item["seq"] > last:
                    last = item["seq"]
                    yield item
        finally:
            subscribers = self._subscribers.get(match_id, [])
            if queue in subscribers:
                subscribers.remove(queue)

    async def close(self, match_id: str) -> None:
        for queue in self._subscribers.pop(match_id, []):
            queue.put_nowait(None)
        self._history.pop(match_id, None)
