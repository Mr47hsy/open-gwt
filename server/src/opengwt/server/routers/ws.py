"""One WebSocket per player per match (docs/protocol/match.md §3 to §5). The handler authenticates,
relays intents to ``MatchService`` and forwards what the event bus publishes, filtered to what
this seat may see. It never holds match state."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from opengwt.core.events import event_for_seat, event_from_dict, event_to_dict
from opengwt.core.intents import intent_from_dict
from opengwt.server.errors import AppError, error_body
from opengwt.server.routers.deps import websocket_player
from opengwt.server.services.matches import STATUS_FINISHED, MatchService

logger = logging.getLogger(__name__)
router = APIRouter()

PROTOCOL = 2
CLOSE_REPLACED = 4000
CLOSE_UNAUTHORISED = 4401
CLOSE_NOT_A_PLAYER = 4403
CLOSE_RATE_LIMITED = 4429
INTENTS_PER_SECOND = 20


class _Connections:
    """Live sockets by (match, seat); a new connection for the same seat replaces the old one."""

    def __init__(self) -> None:
        self._sockets: dict[tuple[str, int], WebSocket] = {}

    async def register(self, match_id: str, seat: int, websocket: WebSocket) -> None:
        previous = self._sockets.get((match_id, seat))
        self._sockets[(match_id, seat)] = websocket
        if previous is not None:
            with contextlib.suppress(Exception):  # the old socket may already be gone
                await previous.close(code=CLOSE_REPLACED)

    def unregister(self, match_id: str, seat: int, websocket: WebSocket) -> None:
        if self._sockets.get((match_id, seat)) is websocket:
            del self._sockets[(match_id, seat)]


connections = _Connections()


def _filtered(events: list[dict[str, Any]], seat: int) -> list[dict[str, Any]]:
    return [event_to_dict(event_for_seat(event_from_dict(e), seat)) for e in events]


async def _send_payload(
    websocket: WebSocket, payload: dict[str, Any], seat: int, with_view: bool = True
) -> bool:
    """Send the events batch (and the view) of one bus payload; True when the match is over."""
    events = _filtered(payload.get("events", []), seat)
    if events:
        await websocket.send_json(
            {"type": "events", "from_seq": events[0]["seq"], "events": events}
        )
    if with_view:
        view = payload["views"][str(seat)]
        await websocket.send_json({"type": "view", "seq": payload["seq"], "view": view})
    if payload.get("over"):
        await websocket.send_json(
            {"type": "match_over", "seq": payload["seq"], "result": payload.get("result")}
        )
        return True
    return False


@router.websocket("/ws/matches/{match_id}")
async def match_socket(websocket: WebSocket, match_id: str, token: str | None = None) -> None:
    app = websocket.app
    service: MatchService = app.state.matches
    renderer = app.state.renderer
    # The close codes of match.md §3 only reach a client over an accepted socket: a close
    # before the accept is a refused handshake (HTTP 403) that shows no code at all.
    try:
        player, locale = await websocket_player(websocket, token)
    except AppError:
        await websocket.accept()
        await websocket.close(code=CLOSE_UNAUTHORISED)
        return
    try:
        info = await service.get_info(match_id)
    except AppError:
        await websocket.accept()
        await websocket.close(code=CLOSE_NOT_A_PLAYER)
        return
    seat = info.seat_of(player.id)
    if seat is None:
        await websocket.accept()
        await websocket.close(code=CLOSE_NOT_A_PLAYER)
        return

    await websocket.accept()
    await connections.register(match_id, seat, websocket)
    await websocket.send_json(
        {
            "type": "hello",
            "protocol": PROTOCOL,
            "pack_hash": app.state.content.pack_hash,
            "match_id": match_id,
            "player_id": player.id,
            "seat": seat,
            "locale": locale,
        }
    )
    try:
        if info.status == STATUS_FINISHED:
            await websocket.send_json({"type": "match_over", "seq": None, "result": info.result})
            await websocket.close()
            return
        since_seq = 0
        current = await service.current(match_id, seat)
        if current is not None:
            since_seq, view = current
            await websocket.send_json({"type": "view", "seq": since_seq, "view": view})
        reader = asyncio.create_task(
            _read_loop(websocket, service, renderer, locale, match_id, seat)
        )
        writer = asyncio.create_task(_write_loop(websocket, service, match_id, seat, since_seq))
        done, pending = await asyncio.wait({reader, writer}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                logger.warning("socket for match %s seat %s ended: %r", match_id, seat, exc)
    finally:
        connections.unregister(match_id, seat, websocket)


async def _write_loop(
    websocket: WebSocket, service: MatchService, match_id: str, seat: int, since_seq: int
) -> None:
    async for payload in service.bus.subscribe(match_id, since_seq):
        if await _send_payload(websocket, payload, seat):
            await websocket.close()
            return


async def _read_loop(
    websocket: WebSocket,
    service: MatchService,
    renderer: Any,
    locale: str,
    match_id: str,
    seat: int,
) -> None:
    window_start = time.monotonic()
    window_count = 0
    while True:
        message = await websocket.receive_json()
        kind = message.get("type")
        if kind == "ping":
            await websocket.send_json({"type": "pong"})
            continue
        if kind == "resync":
            since = int(message.get("since_seq", 0))
            # the missed events for animation, then one view to render from (match.md §9)
            for payload in await service.history(match_id, since):
                await _send_payload(websocket, payload, seat, with_view=False)
            current = await service.current(match_id, seat)
            if current is not None:
                await websocket.send_json({"type": "view", "seq": current[0], "view": current[1]})
            continue
        if kind != "intent":
            error = AppError("unknown_message", 400, {"type": str(kind)})
            await websocket.send_json({"type": "error", **error_body(renderer, locale, error)})
            continue
        now = time.monotonic()
        if now - window_start >= 1.0:
            window_start, window_count = now, 0
        window_count += 1
        if window_count > INTENTS_PER_SECOND:
            await websocket.close(code=CLOSE_RATE_LIMITED)
            return
        intent_id = message.get("intent_id")
        try:
            intent = intent_from_dict(message.get("intent") or {})
            await service.apply(match_id, seat, intent, intent_id)
        except (ValueError, KeyError):
            error = AppError("invalid_request", 400)
            await websocket.send_json(
                {"type": "error", "intent_id": intent_id, **error_body(renderer, locale, error)}
            )
        except AppError as error:
            await websocket.send_json(
                {"type": "error", "intent_id": intent_id, **error_body(renderer, locale, error)}
            )
