"""``MatchService``: the one path through which a match changes (ADR 0008).

``apply`` takes the match lock, loads the state from the store, runs the rules core, appends the
accepted intents to the durable log, lets a server-hosted bot move while the lock is held, saves
with a version check and publishes the events and both views. WebSocket handlers, timers and
bots never touch match state directly.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opengwt.bots import make_bot
from opengwt.core.engine import IllegalIntent, acting_seat, apply, legal_intents, new_match
from opengwt.core.events import Event, event_to_dict
from opengwt.core.intents import Choose, Intent, Mulligan, Pass, intent_from_dict, intent_to_dict
from opengwt.core.model import Deck, MatchState, Phase, Rules
from opengwt.core.replay import MatchRecord, record_to_dict, replay
from opengwt.core.serialize import (
    deck_from_dict,
    deck_to_dict,
    rules_from_dict,
    rules_to_dict,
    state_from_dict,
    state_hash,
    state_to_dict,
)
from opengwt.core.view import player_view
from opengwt.server.backends import EventBus, InlineTaskRunner, MatchStore
from opengwt.server.config import Settings
from opengwt.server.db.models import MatchIntentRow, MatchRow
from opengwt.server.db.session import session_scope
from opengwt.server.errors import AppError
from opengwt.server.services.auth import new_id
from opengwt.server.services.content import Content

logger = logging.getLogger(__name__)

BOT_PLAYER_ID = "bot"
STATUS_WAITING = "waiting"
STATUS_PLAYING = "playing"
STATUS_FINISHED = "finished"
ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
RECENT_INTENT_IDS = 32


@dataclass(frozen=True)
class MatchInfo:
    match_id: str
    mode: str
    status: str
    room_code: str | None
    seed: int
    seats: tuple[str | None, str | None]
    decks: tuple[Deck, Deck] | tuple[Deck]
    rules: Rules
    result: dict[str, Any] | None

    def seat_of(self, player_id: str) -> int | None:
        for seat, occupant in enumerate(self.seats):
            if occupant == player_id:
                return seat
        return None

    @property
    def started(self) -> bool:
        return self.status != STATUS_WAITING


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _info(row: MatchRow) -> MatchInfo:
    decks = tuple(deck_from_dict(d) for d in row.decks)
    return MatchInfo(
        match_id=row.id,
        mode=row.mode,
        status=row.status,
        room_code=row.room_code,
        seed=row.seed,
        seats=(row.seat0_player_id, row.seat1_player_id),
        decks=(decks[0], decks[1]) if len(decks) == 2 else (decks[0],),
        rules=rules_from_dict(row.rules),
        result=row.result,
    )


class MatchService:
    def __init__(
        self,
        content: Content,
        store: MatchStore,
        bus: EventBus,
        sessions: async_sessionmaker[AsyncSession],
        tasks: InlineTaskRunner,
        settings: Settings,
    ) -> None:
        self.content = content
        self.store = store
        self.bus = bus
        self.sessions = sessions
        self.tasks = tasks
        self.settings = settings
        self._deadlines: dict[str, tuple[float, int]] = {}

    # --- lookups ---------------------------------------------------------------------------

    async def get_info(self, match_id: str) -> MatchInfo:
        async with session_scope(self.sessions) as session:
            row = await session.get(MatchRow, match_id)
        if row is None:
            raise AppError("match_not_found", 404)
        return _info(row)

    async def current(self, match_id: str, seat: int) -> tuple[int, dict[str, Any]] | None:
        loaded = await self.store.load(match_id)
        if loaded is None:
            return None
        state = state_from_dict(loaded[0]["state"])
        return state.seq, player_view(self.content.library, state, seat)

    async def history(self, match_id: str, since_seq: int) -> list[dict[str, Any]]:
        return await self.bus.history(match_id, since_seq)

    async def replay_record(self, match_id: str, player_id: str) -> dict[str, Any]:
        info = await self.get_info(match_id)
        if info.seat_of(player_id) is None:
            raise AppError("not_a_player", 403)
        if info.status != STATUS_FINISHED:
            raise AppError("match_not_finished", 409)
        async with session_scope(self.sessions) as session:
            rows = (
                await session.execute(
                    select(MatchIntentRow)
                    .where(MatchIntentRow.match_id == match_id)
                    .order_by(MatchIntentRow.index)
                )
            ).scalars()
            intents = [(r.seat, intent_from_dict(r.intent)) for r in rows]
        assert len(info.decks) == 2
        record = MatchRecord(info.seed, info.decks, tuple(intents), info.rules)
        return {"record": record_to_dict(record), "result": info.result}

    # --- creation --------------------------------------------------------------------------

    async def create_bot_match(self, player_id: str, deck: Deck) -> MatchInfo:
        bot_deck = self._bot_deck(deck)
        info = await self._insert(
            mode="bot",
            status=STATUS_PLAYING,
            room_code=None,
            seats=(player_id, BOT_PLAYER_ID),
            decks=(deck, bot_deck),
        )
        await self._start(info)
        return info

    async def create_room(self, player_id: str, deck: Deck) -> MatchInfo:
        return await self._insert(
            mode="room",
            status=STATUS_WAITING,
            room_code=await self._new_room_code(),
            seats=(player_id, None),
            decks=(deck,),
        )

    async def join_room(self, player_id: str, deck: Deck, room_code: str) -> MatchInfo:
        async with session_scope(self.sessions) as session:
            row = (
                await session.execute(
                    select(MatchRow).where(MatchRow.room_code == room_code.upper())
                )
            ).scalar_one_or_none()
            if row is None:
                raise AppError("room_not_found", 404)
            if row.status != STATUS_WAITING:
                raise AppError("room_full", 409)
            if row.seat0_player_id == player_id:
                raise AppError("own_room", 409)
            row.seat1_player_id = player_id
            row.decks = [*row.decks, deck_to_dict(deck)]
            row.status = STATUS_PLAYING
            info = _info(row)
        await self._start(info)
        return info

    def _bot_deck(self, against: Deck) -> Deck:
        others = [d for d in self.content.starter_decks.values() if d.faction != against.faction]
        pool = others or list(self.content.starter_decks.values())
        return pool[secrets.randbelow(len(pool))]

    async def _new_room_code(self) -> str:
        for _ in range(20):
            code = "".join(
                secrets.choice(ROOM_ALPHABET) for _ in range(self.settings.room_code_length)
            )
            async with session_scope(self.sessions) as session:
                taken = (
                    await session.execute(
                        select(MatchRow.id).where(
                            MatchRow.room_code == code, MatchRow.status == STATUS_WAITING
                        )
                    )
                ).first()
            if taken is None:
                return code
        raise AppError("room_code_exhausted", 503)

    async def _insert(
        self,
        mode: str,
        status: str,
        room_code: str | None,
        seats: tuple[str, str | None],
        decks: tuple[Deck, Deck] | tuple[Deck],
    ) -> MatchInfo:
        row = MatchRow(
            id=new_id(),
            mode=mode,
            status=status,
            room_code=room_code,
            seed=secrets.randbits(31),
            seat0_player_id=seats[0],
            seat1_player_id=seats[1],
            decks=[deck_to_dict(d) for d in decks],
            rules=rules_to_dict(Rules()),
            result=None,
            created_at=_now(),
            finished_at=None,
        )
        async with session_scope(self.sessions) as session:
            session.add(row)
            await session.flush()
            return _info(row)

    async def _start(self, info: MatchInfo) -> None:
        assert len(info.decks) == 2
        async with self.store.lock(info.match_id):
            state, events = new_match(self.content.library, info.decks, info.seed, info.rules)
            data = {"state": state_to_dict(state), "intent_ids": [], "next_index": 0}
            state, events, accepted = await self._bot_moves(info, state, events)
            data = await self._persist(info.match_id, data, state, accepted, version=0)
            await self._publish(info, state, events)

    # --- play ------------------------------------------------------------------------------

    async def apply(
        self, match_id: str, seat: int, intent: Intent, intent_id: str | None = None
    ) -> None:
        info = await self.get_info(match_id)
        if not info.started:
            raise AppError("match_not_started", 409)
        if info.status == STATUS_FINISHED:
            raise AppError("match_over", 409)
        async with self.store.lock(match_id):
            loaded = await self.store.load(match_id)
            if loaded is None:
                raise AppError("match_not_found", 404)
            data, version = loaded
            if intent_id is not None and intent_id in data["intent_ids"]:
                return
            state = state_from_dict(data["state"])
            try:
                state, events = apply(self.content.library, state, seat, intent)
            except IllegalIntent as e:
                raise AppError(
                    e.code, 409, details={"reason": e.reason} if e.reason else None
                ) from e
            accepted = [(seat, intent)]
            state, events, more = await self._bot_moves(info, state, events)
            accepted.extend(more)
            if intent_id is not None:
                data["intent_ids"] = [*data["intent_ids"], intent_id][-RECENT_INTENT_IDS:]
            await self._persist(match_id, data, state, accepted, version)
            await self._publish(info, state, events)

    async def timeout_move(self, match_id: str, seat: int) -> None:
        """When a turn timer expires: pass if legal, otherwise the first legal intent."""
        loaded = await self.store.load(match_id)
        if loaded is None:
            return
        state = state_from_dict(loaded[0]["state"])
        if acting_seat(state) != seat:
            return
        legal = legal_intents(self.content.library, state, seat)
        if not legal:
            return
        chosen: Intent = Pass() if Pass() in legal else legal[0]
        if isinstance(chosen, Mulligan):
            chosen = Mulligan()
        if isinstance(chosen, Choose):
            chosen = Choose(0)
        await self.apply(match_id, seat, chosen)

    async def _bot_moves(
        self, info: MatchInfo, state: MatchState, events: list[Event]
    ) -> tuple[MatchState, list[Event], list[tuple[int, Intent]]]:
        accepted: list[tuple[int, Intent]] = []
        bot_seats = {seat for seat, who in enumerate(info.seats) if who == BOT_PLAYER_ID}
        if not bot_seats:
            return state, events, accepted
        bot = make_bot(self.settings.bot, info.seed)
        guard = 0
        while state.phase is not Phase.MATCH_OVER:
            seat = acting_seat(state)
            if seat is None or seat not in bot_seats:
                break
            legal = legal_intents(self.content.library, state, seat)
            intent = bot.choose(self.content.library, state, seat, legal)
            state, more = apply(self.content.library, state, seat, intent)
            events = events + more
            accepted.append((seat, intent))
            guard += 1
            if guard > 200:
                raise RuntimeError(f"bot did not yield the turn in match {info.match_id}")
        return state, events, accepted

    async def _persist(
        self,
        match_id: str,
        data: dict[str, Any],
        state: MatchState,
        accepted: list[tuple[int, Intent]],
        version: int,
    ) -> dict[str, Any]:
        """Append the accepted intents durably, then save the snapshot (ADR 0008 §4)."""
        start = int(data["next_index"])
        finished = state.phase is Phase.MATCH_OVER
        async with session_scope(self.sessions) as session:
            for offset, (seat, intent) in enumerate(accepted):
                session.add(
                    MatchIntentRow(
                        match_id=match_id,
                        index=start + offset,
                        seat=seat,
                        intent=intent_to_dict(intent),
                    )
                )
            if finished:
                row = await session.get(MatchRow, match_id)
                if row is not None:
                    row.status = STATUS_FINISHED
                    row.finished_at = _now()
                    row.result = self._result(state)
        data = {
            "state": state_to_dict(state),
            "intent_ids": data["intent_ids"],
            "next_index": start + len(accepted),
        }
        await self.store.save(match_id, data, version)
        return data

    @staticmethod
    def _result(state: MatchState) -> dict[str, Any]:
        return {
            "winner": state.winner,
            "rounds": [
                {"round": r.round, "winner": r.winner, "scores": list(r.scores)}
                for r in state.rounds
            ],
            "final_hash": state_hash(state),
        }

    async def _publish(self, info: MatchInfo, state: MatchState, events: list[Event]) -> None:
        over = state.phase is Phase.MATCH_OVER
        payload: dict[str, Any] = {
            "events": [event_to_dict(e) for e in events],
            "views": {str(seat): player_view(self.content.library, state, seat) for seat in (0, 1)},
            "over": over,
        }
        if over:
            payload["result"] = self._result(state)
        await self.bus.publish(info.match_id, state.seq, payload)
        self._schedule_timer(info, state)
        if over:
            self._deadlines.pop(info.match_id, None)
            self.tasks.spawn(self._after_match(info), name=f"after-match:{info.match_id}")

    async def _after_match(self, info: MatchInfo) -> None:
        """Verify the durable record replays to the stored final state, then let go of it."""
        try:
            assert len(info.seats) == 2 and info.seats[0] is not None
            record = await self.replay_record(info.match_id, info.seats[0])
            final, _ = replay(self.content.library, MatchRecord(**_record_kwargs(record)))
            stored = record["result"]["final_hash"] if record["result"] else None
            if state_hash(final) != stored:
                logger.error("match %s: replay hash differs from the stored result", info.match_id)
        finally:
            await asyncio.sleep(0)
            await self.bus.close(info.match_id)
            await self.store.delete(info.match_id)

    # --- timers ----------------------------------------------------------------------------

    def _schedule_timer(self, info: MatchInfo, state: MatchState) -> None:
        timeout = self.settings.turn_timeout_seconds
        if timeout <= 0 or state.phase is Phase.MATCH_OVER:
            return
        seat = acting_seat(state)
        if seat is None or info.seats[seat] == BOT_PLAYER_ID:
            self._deadlines.pop(info.match_id, None)
            return
        self._deadlines[info.match_id] = (asyncio.get_running_loop().time() + timeout, seat)

    async def run_timers(self, interval: float = 1.0) -> None:
        while True:
            await asyncio.sleep(interval)
            now = asyncio.get_running_loop().time()
            due = [(m, seat) for m, (deadline, seat) in self._deadlines.items() if deadline <= now]
            for match_id, seat in due:
                self._deadlines.pop(match_id, None)
                try:
                    await self.timeout_move(match_id, seat)
                except AppError as e:
                    logger.info("timer for %s could not move: %s", match_id, e.code)


def _record_kwargs(payload: dict[str, Any]) -> dict[str, Any]:
    from opengwt.core.replay import record_from_dict

    record = record_from_dict(payload["record"])
    return {
        "seed": record.seed,
        "decks": record.decks,
        "intents": record.intents,
        "rules": record.rules,
    }
