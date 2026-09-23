import asyncio

import pytest

from opengwt.server.backends import MemoryCache, MemoryEventBus, MemoryMatchStore, VersionConflict


async def test_store_versions_and_locks() -> None:
    store = MemoryMatchStore()
    assert await store.load("m") is None
    assert await store.save("m", {"a": 1}, 0) == 1
    with pytest.raises(VersionConflict):
        await store.save("m", {"a": 2}, 0)
    assert await store.save("m", {"a": 2}, 1) == 2
    loaded = await store.load("m")
    assert loaded == ({"a": 2}, 2)
    order: list[str] = []

    async def worker(name: str) -> None:
        async with store.lock("m"):
            order.append(name + ":in")
            await asyncio.sleep(0.01)
            order.append(name + ":out")

    await asyncio.gather(worker("x"), worker("y"))
    assert order == ["x:in", "x:out", "y:in", "y:out"]


async def test_bus_history_and_live_delivery() -> None:
    bus = MemoryEventBus(history=3)
    for seq in (1, 2, 3, 4):
        await bus.publish("m", seq, {"n": seq})
    assert [p["seq"] for p in await bus.history("m", 0)] == [2, 3, 4]  # ring buffer of three
    assert [p["seq"] for p in await bus.history("m", 3)] == [4]

    received: list[int] = []

    async def listen() -> None:
        async for payload in bus.subscribe("m", 2):
            received.append(payload["seq"])
            if payload["seq"] == 6:
                break

    task = asyncio.create_task(listen())
    await asyncio.sleep(0.01)
    await bus.publish("m", 5, {})
    await bus.publish("m", 6, {})
    await asyncio.wait_for(task, 1)
    assert received == [3, 4, 5, 6]
    await bus.close("m")
    assert await bus.history("m", 0) == []


async def test_cache_ttl() -> None:
    cache = MemoryCache()
    await cache.set("k", 1, ttl_seconds=0.01)
    assert await cache.get("k") == 1
    await asyncio.sleep(0.02)
    assert await cache.get("k") is None
    await cache.set("k", 2)
    await cache.delete("k")
    assert await cache.get("k") is None
