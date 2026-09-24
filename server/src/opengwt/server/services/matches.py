"""``MatchService``: the one path through which a match changes (ADR 0008).

``apply`` takes the match lock, loads the state from the store, runs the rules core, appends the
accepted intents to the durable log, lets a server-hosted bot move while the lock is held, saves
with a version check and publishes the events and both views. WebSocket handlers, timers and
bots never touch match state directly.

A match's seed is 256 bits from ``secrets`` (ADR 0010). It stays in the database and the store
until the match is over; the replay record of a finished match is the only place it leaves.
Matches played before ADR 0009 phase B keep their ``opengwt.record/1`` data as history.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opengwt.bots import make_bot
from opengwt.core.engine import (
    IllegalIntent,
    acting_seats,
    apply,
    check_deck,
    legal_intents,
    new_match,
    play_positions,
)
from opengwt.core.events import Event, event_to_dict
from opengwt.core.intents import (
    CancelChoice,
    Choose,
    EndMulligan,
    EndTurn,
    Intent,
    Pass,
    PlayCard,
    UseOrder,
    intent_from_dict,
    intent_to_dict,
)
from opengwt.core.model import Deck, MatchState, Phase, Rules
from opengwt.core.replay import MatchRecord, record_from_dict, record_to_dict, replay
from opengwt.core.rng import bot_stream, parse_seed
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
from opengwt.server.services.decks import problems_to_list

logger = logging.getLogger(__name__)

BOT_PLAYER_ID = "bot"
STATUS_WAITING = "waiting"
STATUS_PLAYING = "playing"
STATUS_FINISHED = "finished"
ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
RECENT_INTENT_IDS = 32
LEGACY_RECORD_SCHEMA = "opengwt.record/1"
BOT_DECISIONS_PER_CALL = 400


def new_seed() -> str:
    """256 bits for a new match, as 64 lowercase hex characters (ADR 0010)."""
    return secrets.token_bytes(32).hex()


def is_v2_seed(seed: str) -> bool:
    try:
        parse_seed(seed)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class MatchInfo:
    """A match row. ``decks`` and ``rules`` stay as stored: a match from before ADR 0009
    phase B has v1 shapes the current core does not read."""

    match_id: str
    mode: str
    status: str
    room_code: str | None
    seed: str
    seats: tuple[str | None, str | None]
    decks: tuple[dict[str, Any], ...]
    rules: dict[str, Any]
    result: dict[str, Any] | None

    @property
    def legacy(self) -> bool:
        return not is_v2_seed(self.seed)

    def core_decks(self) -> tuple[Deck, Deck]:
        assert len(self.decks) == 2 and not self.legacy
        return deck_from_dict(self.decks[0]), deck_from_dict(self.decks[1])

    def core_rules(self) -> Rules:
        return rules_from_dict(self.rules)

    def seat_of(self, player_id: str) -> int | None:
        for seat, occupant in enumerate(self.seats):
            if occupant == player_id:
                return seat
        return None

    @property
    def started(self) -> bool:
        return self.status != STATUS_WAITING


_Wait = tuple[str, int]


def _wait(state: MatchState) -> _Wait:
    """What a player's turn timer runs for (match.md §9). Both players mulligan at once, so the
    mulligan is one wait per player for as long as it lasts, whatever either of them does in
    it; any other wait ends with the next change to the match."""
    if state.phase is Phase.MULLIGAN:
        return ("mulligan", state.round)
    return ("seq", state.seq)


def _keeps_clock(intent: Intent, state: MatchState) -> bool:
    """An activated ability stopped on a choice that can still be cancelled, and the cancelling
    of it, leave the match as it was (cards.md §6.3): the player's turn timer runs on, so using
    an ability and cancelling it cannot buy time (match.md §9)."""
    if isinstance(intent, CancelChoice):
        return True
    return isinstance(intent, UseOrder) and state.pending is not None and state.pending.cancellable


class _Deadline(NamedTuple):
    """A player's turn timer: when it runs out and the wait it was set for."""

    at: float
    wait: _Wait


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _info(row: MatchRow) -> MatchInfo:
    return MatchInfo(
        match_id=row.id,
        mode=row.mode,
        status=row.status,
        room_code=row.room_code,
        seed=row.seed,
        seats=(row.seat0_player_id, row.seat1_player_id),
        decks=tuple(row.decks),
        rules=dict(row.rules),
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
        self._deadlines: dict[tuple[str, int], _Deadline] = {}

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
        return state.seq, player_view(self.content.library, state, seat, match_id)

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
            logged = [(r.seat, r.intent) for r in rows]
        if info.legacy:
            # history from before ADR 0009 phase B, as it was stored; the current core cannot
            # replay it
            legacy = {
                "schema": LEGACY_RECORD_SCHEMA,
                "seed": int(info.seed),
                "rules": info.rules,
                "decks": list(info.decks),
                "intents": [{"seat": seat, "intent": intent} for seat, intent in logged],
            }
            return {"record": legacy, "result": info.result}
        intents = tuple((seat, intent_from_dict(intent)) for seat, intent in logged)
        record = MatchRecord(info.seed, info.core_decks(), intents, info.core_rules())
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
            self._check_room_decks(row, deck)
            row.seat1_player_id = player_id
            row.decks = [*row.decks, deck_to_dict(deck)]
            row.status = STATUS_PLAYING
            info = _info(row)
        await self._start(info)
        return info

    def _check_room_decks(self, row: MatchRow, joining: Deck) -> None:
        """Both decks of a room must be legal under the rules its match will be played with —
        the ones stored when the room was made. The first deck was judged then; if deck building
        has tightened since, the join is refused rather than the match (cards.md §12)."""
        rules = rules_from_dict(row.rules)
        for seat, deck in enumerate((deck_from_dict(row.decks[0]), joining)):
            problems = check_deck(self.content.library, deck, rules)
            if problems:
                raise AppError(
                    "deck_illegal",
                    422,
                    details={"seat": seat, "problems": problems_to_list(problems)},
                )

    def _bot_deck(self, against: Deck) -> Deck:
        """A starter deck of another faction, picked with ``secrets``: which deck the bot plays
        is not part of the match's random stream."""
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
            seed=new_seed(),
            seat0_player_id=seats[0],
            seat1_player_id=seats[1],
            decks=[deck_to_dict(d) for d in decks],
            rules=rules_to_dict(self.content.rules),
            result=None,
            created_at=_now(),
            finished_at=None,
        )
        async with session_scope(self.sessions) as session:
            session.add(row)
            await session.flush()
            return _info(row)

    async def _start(self, info: MatchInfo) -> None:
        async with self.store.lock(info.match_id):
            state, events = new_match(
                self.content.library, info.core_decks(), info.seed, info.core_rules()
            )
            data = {"state": state_to_dict(state), "intent_ids": [], "next_index": 0}
            state, events, accepted = await self._bot_moves(info, state, events, 0)
            data = await self._persist(info.match_id, data, state, accepted, version=0)
            await self._publish(info, state, events)

    # --- play ------------------------------------------------------------------------------

    async def apply(
        self, match_id: str, seat: int, intent: Intent, intent_id: str | None = None
    ) -> None:
        await self._move(match_id, seat, lambda state: [intent], intent_id)

    async def timeout_move(self, match_id: str, seat: int, wait: _Wait) -> None:
        """When a turn timer expires (match.md §9): end the mulligan; cancel a choice — and then
        move on as below, since cancelling alone changes nothing — or pick its first option; end
        the turn once its card is played; pass if the player may; and, after an activated
        ability, when a pass is no longer allowed, play the first card at the right end. The move
        is decided under the match lock and only while the wait the timer was set for goes on, so
        a player's own intent that lands first is never followed by a move they did not make, and
        the other player's redraws in a mulligan neither cancel nor restart it."""
        lib = self.content.library

        def default(state: MatchState) -> Intent | None:
            legal = legal_intents(lib, state, seat)
            if not legal:
                return None
            for intent in (EndMulligan(), CancelChoice(), Choose(0), EndTurn(), Pass()):
                if intent in legal:
                    return intent
            play = next(i for i in legal if isinstance(i, PlayCard))
            if play.row is None:
                return play
            return PlayCard(play.card, play.row, play_positions(lib, state, seat, play) - 1)

        def decide(state: MatchState) -> list[Intent]:
            if seat not in acting_seats(state) or _wait(state) != wait:
                return []
            first = default(state)
            if first is None:
                return []
            if not isinstance(first, CancelChoice):
                return [first]
            cancelled, _ = apply(lib, state, seat, first)
            then = default(cancelled)
            return [first] if then is None else [first, then]

        await self._move(match_id, seat, decide)

    async def _move(
        self,
        match_id: str,
        seat: int,
        decide: Callable[[MatchState], list[Intent]],
        intent_id: str | None = None,
    ) -> None:
        """Apply the intents ``decide`` picks from the current state, in order, all under the
        match lock; none leaves the match as it is."""
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
            intents = decide(state)
            if not intents:
                return
            events: list[Event] = []
            for intent in intents:
                try:
                    state, more = apply(self.content.library, state, seat, intent)
                except IllegalIntent as e:
                    raise AppError(
                        e.code, 409, details={"reason": e.reason} if e.reason else None
                    ) from e
                events.extend(more)
            accepted: list[tuple[int, Intent]] = [(seat, intent) for intent in intents]
            keep_clock = _keeps_clock(intents[-1], state)
            state, events, bot = await self._bot_moves(
                info, state, events, int(data["next_index"]) + len(accepted)
            )
            accepted.extend(bot)
            if intent_id is not None:
                data["intent_ids"] = [*data["intent_ids"], intent_id][-RECENT_INTENT_IDS:]
            await self._persist(match_id, data, state, accepted, version)
            await self._publish(info, state, events, keep_clock)

    async def _bot_moves(
        self, info: MatchInfo, state: MatchState, events: list[Event], log_index: int
    ) -> tuple[MatchState, list[Event], list[tuple[int, Intent]]]:
        """Let a server-hosted bot act while the rules wait on it. Each decision gets a fresh bot
        on its own stream, labelled with the decision's index in the intent log (ADR 0010), so
        the bot keeps no state between calls and its choices say nothing about the match's
        stream."""
        accepted: list[tuple[int, Intent]] = []
        bot_seats = {seat for seat, who in enumerate(info.seats) if who == BOT_PLAYER_ID}
        if not bot_seats:
            return state, events, accepted
        while state.phase is not Phase.MATCH_OVER:
            seat = next((s for s in acting_seats(state) if s in bot_seats), None)
            if seat is None:
                break
            bot = make_bot(self.settings.bot, bot_stream(info.seed, log_index + len(accepted)))
            legal = legal_intents(self.content.library, state, seat)
            intent = bot.choose(self.content.library, state, seat, legal)
            state, more = apply(self.content.library, state, seat, intent)
            events = events + more
            accepted.append((seat, intent))
            if len(accepted) > BOT_DECISIONS_PER_CALL:
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
                {"round": r.round, "winners": list(r.winners), "scores": list(r.scores)}
                for r in state.rounds
            ],
            "final_hash": state_hash(state),
        }

    async def _publish(
        self, info: MatchInfo, state: MatchState, events: list[Event], keep_clock: bool = False
    ) -> None:
        over = state.phase is Phase.MATCH_OVER
        payload: dict[str, Any] = {
            "events": [event_to_dict(e) for e in events],
            "views": {
                str(seat): player_view(self.content.library, state, seat, info.match_id)
                for seat in (0, 1)
            },
            "over": over,
        }
        if over:
            payload["result"] = self._result(state)
        await self.bus.publish(info.match_id, state.seq, payload)
        self._schedule_timer(info, state, keep_clock)
        if over:
            self.tasks.spawn(self._after_match(info), name=f"after-match:{info.match_id}")

    async def _after_match(self, info: MatchInfo) -> None:
        """Verify the durable record replays to the stored final state, then let go of it."""
        try:
            assert len(info.seats) == 2 and info.seats[0] is not None
            record = await self.replay_record(info.match_id, info.seats[0])
            final, _ = replay(self.content.library, record_from_dict(record["record"]))
            stored = record["result"]["final_hash"] if record["result"] else None
            if state_hash(final) != stored:
                logger.error("match %s: replay hash differs from the stored result", info.match_id)
        finally:
            await asyncio.sleep(0)
            await self.bus.close(info.match_id)
            await self.store.delete(info.match_id)

    # --- timers ----------------------------------------------------------------------------

    def _schedule_timer(self, info: MatchInfo, state: MatchState, keep_clock: bool = False) -> None:
        """Give every player the rules wait on a timer, keeping the one they have while its wait
        goes on; a player the rules no longer wait on, or a bot, has none. With ``keep_clock``
        a player's timer runs on through a move that changed nothing (``_keeps_clock``)."""
        timeout = self.settings.turn_timeout_seconds
        if timeout <= 0:
            return
        wait = _wait(state)
        at = asyncio.get_running_loop().time() + timeout
        acting = acting_seats(state)
        for seat in (0, 1):
            key = (info.match_id, seat)
            if seat not in acting or info.seats[seat] == BOT_PLAYER_ID:
                self._deadlines.pop(key, None)
            elif (current := self._deadlines.get(key)) is None:
                self._deadlines[key] = _Deadline(at, wait)
            elif current.wait != wait:
                self._deadlines[key] = _Deadline(current.at if keep_clock else at, wait)

    async def run_timers(self, interval: float = 1.0) -> None:
        """Move for every player whose timer ran out. One match's failure is logged and the loop
        goes on: it serves every match on this worker."""
        while True:
            await asyncio.sleep(interval)
            now = asyncio.get_running_loop().time()
            due = [(key, d) for key, d in self._deadlines.items() if d.at <= now]
            for key, deadline in due:
                if self._deadlines.get(key) != deadline:
                    continue  # re-armed by a move while an earlier timer here was running
                del self._deadlines[key]
                match_id, seat = key
                try:
                    await self.timeout_move(match_id, seat, deadline.wait)
                except AppError as e:
                    logger.info("timer for %s could not move: %s", match_id, e.code)
                except Exception:
                    logger.exception("timer for %s failed", match_id)
