"""The rules engine: ``new_match``, ``apply``, ``legal_intents`` and ``check_deck``.

``apply`` never mutates its input; it copies the state, applies one intent and returns the new
state with the events it produced. Everything that changes a match goes through it. The rules
are docs/protocol/cards.md (``opengwt.cards/2``); section numbers below refer to it.

ADR 0009 phase C gives the triggers their behaviour: what an ability causes — damage reaching
a unit, a boost, a destruction, a unit played — queues the abilities it triggers, which resolve
first in, first out after it (§11.3).
"""

from __future__ import annotations

from typing import Any

from .events import Event
from .intents import (
    CancelChoice,
    Choose,
    EndMulligan,
    Intent,
    Mulligan,
    Pass,
    PlayCard,
    UseOrder,
)
from .model import (
    ARTIFACT_STATUSES,
    AUTOMATIC_STATUSES,
    DEFAULT_RULES,
    PHASE_C_ACTIONS,
    POWER_ACTIONS,
    Ability,
    Action,
    CardDef,
    CardInstance,
    CardPick,
    CardSource,
    ChoiceKind,
    Conditions,
    Deck,
    Invocation,
    Kind,
    Library,
    MatchState,
    MulliganState,
    NextRoundStarter,
    PendingChoice,
    Phase,
    PlayerState,
    RoundResult,
    Row,
    RowEffect,
    RowEffectKind,
    RowPick,
    RowSide,
    Rules,
    Side,
    Status,
    StatusEntry,
    TieRule,
    Trigger,
    Units,
    UnitTarget,
    Where,
    row_effect_class,
)
from .power import Loc, aura_at, board, power_at, score
from .rng import Stream, engine_stream, instance_id, parse_seed


class IllegalIntent(Exception):
    """The intent is not acceptable in this state. ``code`` follows docs/protocol/match.md §10."""

    def __init__(self, code: str, reason: str = "") -> None:
        super().__init__(f"{code}: {reason}" if reason else code)
        self.code = code
        self.reason = reason


NEUTRAL = "neutral"
DUEL_STRIKES_MAX = 64
# Most abilities one resolution resolves; content that triggers itself for ever stops here (§11.3).
QUEUE_STEPS_MAX = 1000


# --- decks --------------------------------------------------------------------------------------


def check_deck(lib: Library, deck: Deck, rules: Rules) -> list[str]:
    """Problems with a deck as message keys (cards.md §12); empty when the deck is legal.

    Phase B checks the shape of a deck; provisions, copies and the unit minimum are phase D.
    """
    problems: list[str] = []
    leader = lib.get(deck.leader)
    if leader is None:
        problems.append(f"error.deck.unknown-card:{deck.leader}")
    elif leader.kind is not Kind.LEADER:
        problems.append(f"error.deck.leader-not-leader:{deck.leader}")
    elif leader.faction not in (deck.faction, NEUTRAL):
        problems.append(f"error.deck.wrong-faction:{deck.leader}")
    stratagem = lib.get(deck.stratagem)
    if stratagem is None:
        problems.append(f"error.deck.unknown-card:{deck.stratagem}")
    elif stratagem.kind is not Kind.STRATAGEM:
        problems.append(f"error.deck.stratagem-not-stratagem:{deck.stratagem}")
    elif stratagem.faction not in (deck.faction, NEUTRAL):
        problems.append(f"error.deck.wrong-faction:{deck.stratagem}")
    for cid in deck.cards:
        defn = lib.get(cid)
        if defn is None:
            problems.append(f"error.deck.unknown-card:{cid}")
            continue
        if defn.faction not in (deck.faction, NEUTRAL):
            problems.append(f"error.deck.wrong-faction:{cid}")
        if defn.kind is Kind.LEADER:
            problems.append(f"error.deck.leader-in-deck:{cid}")
        elif defn.kind is Kind.STRATAGEM:
            problems.append(f"error.deck.stratagem-in-deck:{cid}")
        elif defn.token:
            problems.append(f"error.deck.token-in-deck:{cid}")
    if len(deck.cards) < rules.deck_min_cards:
        problems.append("error.deck.too-few-cards")
    if len(deck.cards) > rules.deck_max_cards:
        problems.append("error.deck.too-many-cards")
    return list(dict.fromkeys(problems))


# --- public API ---------------------------------------------------------------------------------


def new_match(
    lib: Library, decks: tuple[Deck, Deck], seed: str, rules: Rules = DEFAULT_RULES
) -> tuple[MatchState, list[Event]]:
    """Allocate and shuffle, decide who starts, and begin round one with its draws and mulligan
    (§11.5). ``seed`` is 64 lowercase hex characters (ADR 0010)."""
    parse_seed(seed)
    for seat, deck in enumerate(decks):
        problems = check_deck(lib, deck, rules)
        if problems:
            raise ValueError(f"deck for seat {seat} is not legal: {', '.join(problems)}")
    state = MatchState(
        rules=rules,
        seed=seed,
        rng_block=0,
        rng_pos=0,
        next_instance=0,
        phase=Phase.MULLIGAN,
        round=1,
        starter=0,
        turn=None,
        active=0,
        players=[],
        seq=0,
        winner=None,
        pending=None,
        resolving=[],
        rounds=[],
    )
    ctx = _Ctx(lib, state)
    for seat, deck in enumerate(decks):
        cards = [ctx.new_instance(cid, seat) for cid in deck.cards]
        leader = ctx.new_instance(deck.leader, seat)
        state.players.append(
            PlayerState(
                seat=seat,
                faction=deck.faction,
                deck=cards,
                hand=[],
                graveyard=[],
                banished=[],
                rows={row: RowSide() for row in rules.rows},
                leader=leader,
                deck_had_neutral=any(lib[c].faction == NEUTRAL for c in deck.cards),
            )
        )
    for player in state.players:
        ctx.rng.shuffle(player.deck)
    state.starter = state.active = ctx.rng.below(2)
    # no seed: events reach clients, and the seed with the open-source shuffle rebuilds both decks
    ctx.emit("match_started", starter=state.starter)
    if rules.starter_stratagem:
        ctx.place_stratagem(state.starter, decks[state.starter].stratagem)
    ctx.start_round()
    ctx.save_rng()
    return state, ctx.events


def apply(
    lib: Library, state: MatchState, seat: int, intent: Intent
) -> tuple[MatchState, list[Event]]:
    """Apply one intent for ``seat``. Raises ``IllegalIntent``; never mutates ``state``."""
    if seat not in (0, 1):
        raise IllegalIntent("unauthorised")
    if state.phase is Phase.MATCH_OVER:
        raise IllegalIntent("match_over")
    new = state.clone()
    ctx = _Ctx(lib, new)
    if isinstance(intent, Mulligan):
        ctx.mulligan(seat, intent.card)
    elif isinstance(intent, EndMulligan):
        ctx.end_mulligan(seat)
    elif isinstance(intent, Choose):
        ctx.choose(seat, intent.option)
    elif isinstance(intent, CancelChoice):
        ctx.cancel_choice(seat)
    else:
        if new.phase is Phase.MULLIGAN:
            raise IllegalIntent("illegal_intent", "error.intent.mulligan-phase")
        if new.phase is Phase.CHOOSING:
            raise IllegalIntent("choice_pending")
        if new.turn != seat:
            raise IllegalIntent("not_your_turn")
        if isinstance(intent, PlayCard):
            ctx.play_card(seat, intent.card, intent.row, intent.position)
        elif isinstance(intent, UseOrder):
            ctx.use_order(seat, intent.instance)
        elif isinstance(intent, Pass):
            ctx.do_pass(seat)
        else:
            raise IllegalIntent("illegal_intent", "error.intent.unknown")
    ctx.save_rng()
    return new, ctx.events


def legal_intents(lib: Library, state: MatchState, seat: int) -> list[Intent]:
    """Exactly the intents ``apply`` would accept from ``seat`` right now, compressed as
    docs/protocol/match.md §6 says: a ``PlayCard`` of a unit or artifact without ``position``
    stands for every position from 0 to the number of cards on that row-side."""
    if state.phase is Phase.MATCH_OVER:
        return []
    player = state.players[seat]
    if state.phase is Phase.MULLIGAN:
        m = player.mulligan
        if m is None or m.done:
            return []
        out: list[Intent] = []
        if m.remaining > 0 and player.deck:
            out.extend(Mulligan(c.instance) for c in player.hand)
        out.append(EndMulligan())
        return out
    if state.phase is Phase.CHOOSING:
        pending = state.pending
        if pending is None or pending.seat != seat:
            return []
        choices: list[Intent] = [Choose(i) for i in range(len(pending.options))]
        if pending.cancellable:
            choices.append(CancelChoice())
        return choices
    if state.turn != seat:
        return []
    plays: list[Intent] = [Pass()]
    for loc in board(state, seat):
        if loc.seat == seat and order_ready(lib, state, seat, loc.card):
            plays.append(UseOrder(loc.card.instance))
    for inst in player.hand:
        defn = lib[inst.card]
        if defn.placed:
            land = _landing_seat(state, seat, defn)
            for row in _allowed_rows(state.rules, defn):
                if len(state.players[land].rows[row].cards) < state.rules.row_capacity:
                    plays.append(PlayCard(inst.instance, row))
        elif defn.kind is Kind.SPECIAL:
            plays.append(PlayCard(inst.instance))
    return plays


def play_positions(lib: Library, state: MatchState, seat: int, intent: PlayCard) -> int:
    """How many positions a compressed ``PlayCard`` of ``legal_intents`` stands for: 0 for a
    special, otherwise the number of cards on the row-side plus one."""
    defn = lib[_hand_card(state, seat, intent.card).card]
    if intent.row is None or not defn.placed:
        return 0
    land = _landing_seat(state, seat, defn)
    return len(state.players[land].rows[intent.row].cards) + 1


def acting_seats(state: MatchState) -> tuple[int, ...]:
    """The seats the rules are waiting on: both players during a mulligan until each is done,
    the chooser while a choice is pending, otherwise the player whose turn it is."""
    if state.phase is Phase.MULLIGAN:
        order = (state.starter, 1 - state.starter)
        return tuple(
            s for s in order if (m := state.players[s].mulligan) is not None and not m.done
        )
    if state.phase is Phase.CHOOSING:
        return (state.pending.seat,) if state.pending is not None else ()
    if state.phase is Phase.PLAYING and state.turn is not None:
        return (state.turn,)
    return ()


def acting_seat(state: MatchState) -> int | None:
    seats = acting_seats(state)
    return seats[0] if seats else None


def order_ready(lib: Library, state: MatchState, seat: int, card: CardInstance) -> bool:
    """Whether ``seat`` may use this card's activated ability now (§6.3): its controller's turn,
    not passed, no choice pending, the card on their side of the board, not locked, a charge
    left, no cooldown, and a candidate for its first ability if that one asks for a choice.

    Activated abilities are ADR 0009 phase C; since ADR 0011 a stratagem's is used in phase B,
    so only a stratagem is ever ready until phase C."""
    d = lib[card.card]
    if d.kind is not Kind.STRATAGEM or d.activation is None:
        return False
    if state.phase is not Phase.PLAYING or state.turn != seat or state.players[seat].passed:
        return False
    if card.has(Status.LOCKED) or card.cooldown > 0:
        return False
    if card.charges is not None and card.charges <= 0:
        return False
    if all(c is not card for side in state.players[seat].rows.values() for c in side.cards):
        return False
    first = next((a for a in d.abilities if a.when is Trigger.ON_ACTIVATE), None)
    if first is None:
        return False
    if first.target is not None and first.target.units is Units.CHOSEN:
        return bool(_Ctx(lib, state).unit_candidates(seat, card, first.target, first.do))
    return True


# --- helpers shared by the API and the context ----------------------------------------------------


def _allowed_rows(rules: Rules, defn: CardDef) -> tuple[Row, ...]:
    if not defn.rows:
        return rules.rows
    return tuple(r for r in rules.rows if r in defn.rows)


def _landing_seat(state: MatchState, seat: int, defn: CardDef) -> int:
    return state.other(seat) if defn.kind is Kind.UNIT and defn.side is Side.OPPONENT else seat


def _hand_card(state: MatchState, seat: int, instance_id_: str) -> CardInstance:
    for inst in state.players[seat].hand:
        if inst.instance == instance_id_:
            return inst
    raise IllegalIntent("unknown_instance", instance_id_)


def _seats_for(state: MatchState, seat: int, side: Side | None) -> tuple[int, ...]:
    if side is Side.OPPONENT:
        return (state.other(seat),)
    if side is Side.BOTH:
        return (seat, state.other(seat))
    return (seat,)


def _status_fields(entry: StatusEntry) -> dict[str, Any]:
    out: dict[str, Any] = {"status": entry.status.value}
    if entry.turns is not None:
        out["turns"] = entry.turns
    return out


# --- the context of one application ---------------------------------------------------------------


class _Ctx:
    """One application of one intent: the state being mutated, its RNG and the events so far."""

    def __init__(self, lib: Library, state: MatchState) -> None:
        self.lib = lib
        self.s = state
        self.events: list[Event] = []
        self.rng: Stream = engine_stream(state.seed, state.rng_block, state.rng_pos)
        self._checking = False
        # the resolution queue (§11.3): what is left of it lives in a pending choice meanwhile
        self.queue: list[Invocation] = []
        self.resolved = 0
        # the activated ability whose abilities are resolving, and whether it spent its charge
        self.order: str | None = None
        self.order_started = True
        # a choice is only ever asked while a played card or an activated ability resolves
        self.may_ask = False
        # the aura of every unit on the board as last reported; see ``sync_auras``
        self._aura: dict[str, int] = self.auras() if state.players else {}

    # --- plumbing ------------------------------------------------------------------------------

    def save_rng(self) -> None:
        self.s.rng_block = self.rng.block
        self.s.rng_pos = self.rng.pos

    def emit(self, type_: str, **data: Any) -> None:
        self.s.seq += 1
        self.events.append(Event(self.s.seq, type_, data))

    def new_instance(self, card_id: str, owner: int) -> CardInstance:
        """A new card instance with the next opaque id (ADR 0010); a collision is skipped."""
        taken = {c.instance for c in self.all_cards()}
        while True:
            iid = instance_id(self.s.seed, self.s.next_instance)
            self.s.next_instance += 1
            if iid not in taken:
                break
        inst = CardInstance(iid, card_id, owner)
        self.reset(inst)
        return inst

    def all_cards(self) -> list[CardInstance]:
        cards: list[CardInstance] = list(self.s.resolving)
        for p in self.s.players:
            cards.extend(p.deck)
            cards.extend(p.hand)
            cards.extend(p.graveyard)
            cards.extend(p.banished)
            for side in p.rows.values():
                cards.extend(side.cards)
            if p.leader is not None:
                cards.append(p.leader)
        return cards

    def defn(self, card: CardInstance) -> CardDef:
        return self.lib[card.card]

    def reset(self, card: CardInstance) -> None:
        """A card's state off the board: its definition, with the charges of its activated
        ability (a leader keeps its own for the whole match)."""
        d = self.defn(card)
        card.base = card.power = d.power
        card.armor = 0
        card.statuses = []
        card.charges = d.activation.charges if d.activation is not None else None
        card.cooldown = 0

    # --- board queries -------------------------------------------------------------------------

    def board(self) -> list[Loc]:
        return board(self.s)

    def loc(self, iid: str) -> Loc | None:
        for seat in (0, 1):
            for row, side in self.s.players[seat].rows.items():
                for i, c in enumerate(side.cards):
                    if c.instance == iid:
                        return Loc(seat, row, i, c)
        return None

    def is_unit(self, card: CardInstance) -> bool:
        return self.defn(card).kind is Kind.UNIT

    def power(self, loc: Loc) -> int:
        return power_at(self.lib, self.s, loc.seat, loc.row, loc.index)

    def power_of(self, card: CardInstance) -> int:
        """Power for filters: current power on the board, printed power elsewhere."""
        loc = self.loc(card.instance)
        if loc is not None:
            return self.power(loc)
        return self.defn(card).power

    def auras(self) -> dict[str, int]:
        return {
            loc.card.instance: aura_at(self.lib, self.s, loc.seat, loc.row, loc.index)
            for loc in self.board()
            if self.is_unit(loc.card)
        }

    def sync_auras(self) -> None:
        """Report every aura that changed since the last call as ``power_changed`` (reason
        ``aura``). Called right after each change that can move an aura — a card entering,
        leaving or moving, a lock added or removed — so the event carries the power before and
        after that change alone."""
        current = self.auras()
        for loc in self.board():
            iid = loc.card.instance
            old, new = self._aura.get(iid), current.get(iid)
            if old is None or new is None or old == new:
                continue
            self.emit(
                "power_changed",
                seat=loc.seat,
                instance=iid,
                card=loc.card.card,
                reason="aura",
                source=None,
                **{"from": loc.card.power + old, "to": loc.card.power + new},
            )
        self._aura = current

    def pick_random(self, items: list[Loc], count: int) -> list[Loc]:
        """``count`` distinct items drawn with the seeded PRNG, returned in board order."""
        pool = list(range(len(items)))
        chosen: list[int] = []
        for _ in range(min(count, len(pool))):
            chosen.append(pool.pop(self.rng.below(len(pool))))
        return [items[i] for i in sorted(chosen)]

    def pick_extreme(self, items: list[Loc], strongest: bool) -> list[Loc]:
        if not items:
            return []
        powers = [self.power(loc) for loc in items]
        best = max(powers) if strongest else min(powers)
        tied = [loc for loc, p in zip(items, powers, strict=True) if p == best]
        return [tied[self.rng.below(len(tied))]] if len(tied) > 1 else tied

    # --- filters -------------------------------------------------------------------------------

    def where_ok(self, card: CardInstance, where: Where, acting: CardInstance | None) -> bool:
        d = self.defn(card)
        if where.color is not None and d.color is not where.color:
            return False
        if any(t in d.tags for t in where.tags_none):
            return False
        if where.tags_any and not any(t in d.tags for t in where.tags_any):
            return False
        on_board = self.loc(card.instance) is not None
        statuses = {e.status for e in card.statuses} if on_board else set()
        if any(st in statuses for st in where.statuses_none):
            return False
        if where.statuses_any and not any(st in statuses for st in where.statuses_any):
            return False
        if where.same_id_as_this and (acting is None or card.card != acting.card):
            return False
        if where.power_at_least is not None or where.power_at_most is not None:
            p = self.power_of(card) if d.kind is Kind.UNIT else 0
            if where.power_at_least is not None and p < where.power_at_least:
                return False
            if where.power_at_most is not None and p > where.power_at_most:
                return False
        if where.stronger_than_this:
            if acting is None or not self.is_unit(acting) or self.loc(acting.instance) is None:
                return False
            if d.kind is not Kind.UNIT or self.power_of(card) <= self.power_of(acting):
                return False
        if where.boosted and not (on_board and d.kind is Kind.UNIT and card.power > card.base):
            return False
        return not (
            where.damaged and not (on_board and d.kind is Kind.UNIT and card.power < card.base)
        )

    def is_candidate(
        self, loc: Loc, acting: CardInstance | None, t: UnitTarget, action: Action
    ) -> bool:
        """A card a unit selector may take (§7.1): of the filter's kinds — units by default, only
        units for a power action, never a stratagem — matching the filter, not the acting card."""
        kinds = t.where.kind or (Kind.UNIT,)
        if action in POWER_ACTIONS:
            kinds = tuple(k for k in kinds if k is Kind.UNIT)
        c = loc.card
        if acting is not None and c.instance == acting.instance:
            return False
        return self.defn(c).kind in kinds and self.where_ok(c, t.where, acting)

    def unit_candidates(
        self, seat: int, acting: CardInstance | None, t: UnitTarget, action: Action
    ) -> list[Loc]:
        """The candidates of a sided selector (§7.1): cards on the side and rows that match the
        filter, the acting card excluded; for ``chosen``, immune units and the units a guard
        protects are excluded too."""
        seats = _seats_for(self.s, seat, t.side)
        out: list[Loc] = []
        for loc in self.board():
            if loc.seat not in seats or (t.rows is not None and loc.row not in t.rows):
                continue
            if self.is_candidate(loc, acting, t, action):
                out.append(loc)
        if t.units is Units.CHOSEN:
            guarded = {
                (loc.seat, loc.row)
                for loc in self.board()
                if loc.seat != seat and loc.card.has(Status.GUARDING)
            }
            out = [
                loc
                for loc in out
                if not loc.card.has(Status.IMMUNE)
                and ((loc.seat, loc.row) not in guarded or loc.card.has(Status.GUARDING))
            ]
        return out

    def select_units(
        self, inv: Invocation, acting: CardInstance | None, t: UnitTarget, action: Action
    ) -> list[Loc]:
        """The targets of a selector that asks nobody (everything but ``chosen``), in board
        order."""
        seat = inv.seat
        if t.units is Units.THIS:
            loc = self.loc(acting.instance) if acting is not None else None
            if loc is None or (action in POWER_ACTIONS and not self.is_unit(loc.card)):
                return []
            if self.defn(loc.card).kind is Kind.STRATAGEM:
                return []  # nothing acts on a stratagem (ADR 0011)
            return [loc] if self.where_ok(loc.card, t.where, acting) else []
        if t.units is Units.ADJACENT:
            here = self.loc(acting.instance) if acting is not None else None
            if here is None:
                return []
            return [
                loc
                for loc in self.board()
                if loc.seat == here.seat
                and loc.row is here.row
                and abs(loc.index - here.index) == 1
                and self.is_candidate(loc, acting, t, action)
            ]
        if t.units in (Units.TRIGGER_UNIT, Units.PREVIOUS_TARGETS):
            wanted = [inv.trigger] if t.units is Units.TRIGGER_UNIT else inv.previous or []
            return [
                loc
                for loc in self.board()
                if loc.card.instance in wanted and self.is_candidate(loc, acting, t, action)
            ]
        if t.units is Units.CHOSEN_ROW:
            return []  # a choice of kind row: phase C, generalised choices
        cands = self.unit_candidates(seat, acting, t, action)
        if t.units is Units.ALL:
            return cands
        if t.units is Units.RANDOM:
            return self.pick_random(cands, t.count)
        if t.units is Units.STRONGEST:
            return self.pick_extreme(cands, strongest=True)
        if t.units is Units.WEAKEST:
            return self.pick_extreme(cands, strongest=False)
        return []

    def conditions_hold(self, inv: Invocation, acting: CardInstance | None, c: Conditions) -> bool:
        if c.on_row is not None:
            loc = self.loc(acting.instance) if acting is not None else None
            row = inv.row if inv.row is not None else loc.row if loc is not None else None
            if row is not c.on_row:
                return False
        if c.trigger_unit is not None:
            trigger = self.card_by_id(inv.trigger) if inv.trigger is not None else None
            if trigger is None or not self.where_ok(trigger, c.trigger_unit, acting):
                return False
        if c.this is not None and (acting is None or not self.where_ok(acting, c.this, acting)):
            return False
        if c.hand_at_most is not None and len(self.s.players[inv.seat].hand) > c.hand_at_most:
            return False
        if c.starting_deck_without_neutral and self.s.players[inv.seat].deck_had_neutral:
            return False
        if c.units_at_least is not None:
            cond = c.units_at_least
            count_target = UnitTarget(Units.ALL, cond.side, cond.rows, 1, cond.where)
            if len(self.unit_candidates(inv.seat, acting, count_target, Action.DESTROY)) < (
                cond.count
            ):
                return False
        return True

    # --- entering and leaving the board --------------------------------------------------------

    def enter(
        self, card: CardInstance, seat: int, row: Row, position: int, extra: tuple[Status, ...] = ()
    ) -> Loc:
        """Put a card onto a row-side with fresh board state and its innate statuses (§9)."""
        d = self.defn(card)
        self.reset(card)
        card.armor = d.armor
        card.statuses = [StatusEntry(st) for st in d.statuses]
        card.statuses.extend(StatusEntry(st) for st in extra if st not in d.statuses)
        if seat != card.owner:
            card.statuses.append(StatusEntry(Status.ON_ENEMY_SIDE))
        if d.activation is not None and not d.activation.ready_on_play:
            card.cooldown = 1
        self.s.players[seat].rows[row].cards.insert(position, card)
        return Loc(seat, row, position, card)

    def arrive(self, card: CardInstance) -> None:
        """A unit entering a row-side with ``damage_on_arrival`` takes its damage (§10)."""
        loc = self.loc(card.instance)
        if loc is None or not self.is_unit(card):
            return
        effect = self.s.players[loc.seat].rows[loc.row].effect
        if effect is not None and effect.effect is RowEffectKind.DAMAGE_ON_ARRIVAL:
            self.damage(card.instance, effect.amount, effect.effect.value, None)

    def banished_on_leave(self, card: CardInstance) -> bool:
        """A card with ``banish_on_leave`` is banished whenever it leaves the board, and so are a
        token whatever its statuses and a stratagem: they never reach a hand, deck or graveyard
        (§3, §9, ADR 0011)."""
        d = self.defn(card)
        return card.has(Status.BANISH_ON_LEAVE) or d.token or d.kind is Kind.STRATAGEM

    def leave(self, loc: Loc) -> bool:
        """Take a card off the board to its owner's graveyard, or banish it (see
        ``banished_on_leave``). Returns True when it was banished."""
        card = loc.card
        banished = self.banished_on_leave(card)
        self.s.players[loc.seat].rows[loc.row].cards.remove(card)
        self.reset(card)
        owner = self.s.players[card.owner]
        (owner.banished if banished else owner.graveyard).append(card)
        return banished

    def check_destruction(self) -> None:
        """Destroy every unit whose power is zero or less, in board order, until none is (§11.2)."""
        if self._checking:
            return
        self._checking = True
        try:
            while True:
                doomed = next(
                    (
                        loc
                        for loc in self.board()
                        if self.is_unit(loc.card) and self.power(loc) <= 0
                    ),
                    None,
                )
                if doomed is None:
                    return
                self.destroy_at(doomed, None)
        finally:
            self._checking = False

    def destroy(self, iid: str, source: str | None) -> None:
        loc = self.loc(iid)
        if loc is not None:
            self.destroy_at(loc, source)

    def destroy_at(self, loc: Loc, source: str | None) -> None:
        """§11.2: to the graveyard or banished; then, unless the card was locked, its
        ``on_destroyed`` abilities are queued for its controller, remembering the row it was on."""
        card = loc.card
        locked = card.has(Status.LOCKED)
        banished = self.leave(loc)
        self.emit(
            "card_destroyed",
            seat=loc.seat,
            instance=card.instance,
            card=card.card,
            row=loc.row.value,
            banished=banished,
            source=source,
        )
        if not locked:
            self.fire(card, Trigger.ON_DESTROYED, loc.seat, row=loc.row)
        self.sync_auras()
        self.check_destruction()

    def banish(self, iid: str, source: str | None) -> None:
        loc = self.loc(iid)
        if loc is None:
            return
        card = loc.card
        self.s.players[loc.seat].rows[loc.row].cards.remove(card)
        self.reset(card)
        self.s.players[card.owner].banished.append(card)
        self.emit("card_banished", seat=loc.seat, instance=card.instance, card=card.card)
        self.sync_auras()
        self.check_destruction()

    def return_to_hand(self, iid: str, source: str | None) -> None:
        loc = self.loc(iid)
        if loc is None:
            return
        card = loc.card
        owner = self.s.players[card.owner]
        if len(owner.hand) >= self.s.rules.hand_limit:
            return
        if self.leave_to_hand(loc):
            self.emit("card_banished", seat=loc.seat, instance=card.instance, card=card.card)
        else:
            self.emit("card_returned", seat=loc.seat, instance=card.instance, card=card.card)
        self.sync_auras()
        self.check_destruction()

    def leave_to_hand(self, loc: Loc) -> bool:
        card = loc.card
        banished = self.banished_on_leave(card)
        self.s.players[loc.seat].rows[loc.row].cards.remove(card)
        self.reset(card)
        owner = self.s.players[card.owner]
        (owner.banished if banished else owner.hand).append(card)
        return banished

    def move_to_other_row(self, iid: str) -> None:
        loc = self.loc(iid)
        if loc is None:
            return
        others = [r for r in self.s.rules.rows if r is not loc.row]
        if not others:
            return
        to_row = others[0]
        target = self.s.players[loc.seat].rows[to_row]
        if len(target.cards) >= self.s.rules.row_capacity:
            return
        self.s.players[loc.seat].rows[loc.row].cards.remove(loc.card)
        target.cards.append(loc.card)
        self.emit(
            "card_moved",
            seat=loc.seat,
            instance=loc.card.instance,
            card=loc.card.card,
            from_row=loc.row.value,
            to_row=to_row.value,
            position=len(target.cards) - 1,
        )
        self.sync_auras()
        self.arrive(loc.card)
        self.check_destruction()

    def take_control(self, iid: str, seat: int, source: str | None) -> None:
        loc = self.loc(iid)
        if loc is None or loc.seat == seat:
            return
        target = self.s.players[seat].rows[loc.row]
        if len(target.cards) >= self.s.rules.row_capacity:
            return
        card = loc.card
        self.s.players[loc.seat].rows[loc.row].cards.remove(card)
        target.cards.append(card)
        card.statuses = [e for e in card.statuses if e.status is not Status.ON_ENEMY_SIDE]
        if seat != card.owner:
            card.statuses.append(StatusEntry(Status.ON_ENEMY_SIDE))
        self.emit(
            "control_changed",
            seat=seat,
            instance=card.instance,
            card=card.card,
            from_seat=loc.seat,
            row=loc.row.value,
            position=len(target.cards) - 1,
            source=source,
        )
        self.sync_auras()
        self.arrive(card)
        self.check_destruction()

    def placement(
        self,
        card: CardInstance,
        seat: int,
        acting: CardInstance | None,
        row: Row | None,
        after: CardInstance | None = None,
        last_row: Row | None = None,
    ) -> tuple[Row, int] | None:
        """Where ``summon_from_deck`` and ``place_new_card`` put a card (§8): on ``row`` if
        given, else the acting card's row — ``last_row``, the row it was last on, once it has
        left the board — else the first row the card allows; right of the card placed before it
        by the same ability (``after``), else right of the acting card on that row-side, else at
        the right end. ``None`` when that row-side is full."""
        allowed = _allowed_rows(self.s.rules, self.defn(card))
        if not allowed:
            return None
        acting_loc = self.loc(acting.instance) if acting is not None else None
        acting_row = acting_loc.row if acting_loc is not None else last_row
        chosen = row or acting_row or allowed[0]
        if chosen not in allowed:
            chosen = allowed[0]
        side = self.s.players[seat].rows[chosen]
        if len(side.cards) >= self.s.rules.row_capacity:
            return None
        for anchor in (after, acting):
            anchor_loc = self.loc(anchor.instance) if anchor is not None else None
            if anchor_loc is not None and anchor_loc.seat == seat and anchor_loc.row is chosen:
                return chosen, anchor_loc.index + 1
        return chosen, len(side.cards)

    def summon(
        self,
        card: CardInstance,
        seat: int,
        where: tuple[Row, int],
        acting_seat: int,
        from_: str,
        extra: tuple[Status, ...] = (),
    ) -> None:
        """Put a card onto the board without playing it: no ``on_play``, no ``on_ally_played``."""
        row, position = where
        self.enter(card, seat, row, position, extra)
        self.emit(
            "card_summoned",
            seat=acting_seat,
            instance=card.instance,
            card=card.card,
            **{"from": from_},
            row=row.value,
            position=position,
            side="self" if seat == acting_seat else "opponent",
        )
        self.sync_auras()
        self.arrive(card)
        self.check_destruction()

    # --- power ---------------------------------------------------------------------------------

    def damage(
        self, iid: str, amount: int, reason: str, source: str | None, pierce_armor: bool = False
    ) -> int:
        """One instance of damage (§11.2). Returns the damage that reached power."""
        loc = self.loc(iid)
        if loc is None or not self.is_unit(loc.card) or amount <= 0:
            return 0
        card = loc.card
        if card.has(Status.SHIELDED):
            self.emit(
                "damage_blocked",
                seat=loc.seat,
                instance=card.instance,
                card=card.card,
                amount=amount,
                reason=reason,
                source=source,
            )
            self.drop_status(loc, Status.SHIELDED, "blocked", source)
            return 0
        rest = amount
        if not pierce_armor and card.armor > 0:
            absorbed = min(card.armor, amount)
            before = card.armor
            card.armor -= absorbed
            rest -= absorbed
            self.emit(
                "armor_changed",
                seat=loc.seat,
                instance=card.instance,
                card=card.card,
                reason=reason,
                source=source,
                **{"from": before, "to": card.armor},
            )
        if rest <= 0:
            return 0
        card.power -= rest
        self.emit(
            "unit_damaged",
            seat=loc.seat,
            instance=card.instance,
            card=card.card,
            amount=rest,
            power=self.power(loc),
            reason=reason,
            source=source,
        )
        self.check_destruction()
        survivor = self.loc(iid)
        if survivor is not None:
            self.fire(card, Trigger.ON_DAMAGED, survivor.seat)
        return rest

    def boost(self, iid: str, amount: int, reason: str, source: str | None) -> None:
        loc = self.loc(iid)
        if loc is None or not self.is_unit(loc.card) or amount <= 0:
            return
        loc.card.power += amount
        self.emit(
            "unit_boosted",
            seat=loc.seat,
            instance=loc.card.instance,
            card=loc.card.card,
            amount=amount,
            power=self.power(loc),
            reason=reason,
            source=source,
        )
        self.fire(loc.card, Trigger.ON_BOOSTED, loc.seat)

    def heal(self, iid: str, source: str | None) -> None:
        loc = self.loc(iid)
        if loc is None or not self.is_unit(loc.card) or loc.card.power >= loc.card.base:
            return
        amount = loc.card.base - loc.card.power
        loc.card.power = loc.card.base
        self.emit(
            "unit_healed",
            seat=loc.seat,
            instance=loc.card.instance,
            card=loc.card.card,
            amount=amount,
            power=self.power(loc),
            source=source,
        )

    def reset_power(self, iid: str, source: str | None) -> None:
        loc = self.loc(iid)
        if loc is None or not self.is_unit(loc.card) or loc.card.power == loc.card.base:
            return
        before = self.power(loc)
        loc.card.power = loc.card.base
        self.emit(
            "power_changed",
            seat=loc.seat,
            instance=loc.card.instance,
            card=loc.card.card,
            reason="reset_power",
            source=source,
            **{"from": before, "to": self.power(loc)},
        )
        self.check_destruction()

    def raise_base_power(self, iid: str, amount: int, source: str | None) -> None:
        loc = self.loc(iid)
        if loc is None or not self.is_unit(loc.card):
            return
        before = loc.card.base
        loc.card.base += amount
        loc.card.power += amount
        self.emit(
            "base_power_changed",
            seat=loc.seat,
            instance=loc.card.instance,
            card=loc.card.card,
            power=self.power(loc),
            source=source,
            **{"from": before, "to": loc.card.base},
        )

    def add_armor(self, iid: str, amount: int, source: str | None) -> None:
        loc = self.loc(iid)
        if loc is None or not self.is_unit(loc.card):
            return
        before = loc.card.armor
        loc.card.armor += amount
        self.emit(
            "armor_changed",
            seat=loc.seat,
            instance=loc.card.instance,
            card=loc.card.card,
            reason="add_armor",
            source=source,
            **{"from": before, "to": loc.card.armor},
        )

    # --- statuses ------------------------------------------------------------------------------

    def drop_status(self, loc: Loc, status: Status, reason: str, source: str | None) -> None:
        card = loc.card
        card.statuses = [e for e in card.statuses if e.status is not status]
        self.emit(
            "status_removed",
            seat=loc.seat,
            instance=card.instance,
            card=card.card,
            status=status.value,
            reason=reason,
            source=source,
        )
        self.sync_auras()

    def add_status(
        self, iid: str, status: Status, turns: int | None, reason: str, source: str | None
    ) -> None:
        """§9: poison twice destroys; bleeding and growing cancel each other turn for turn; timed
        statuses add up; nothing reaches a card with ``status_proof``."""
        loc = self.loc(iid)
        if loc is None or status in AUTOMATIC_STATUSES:
            return
        card = loc.card
        if not self.is_unit(card) and status not in ARTIFACT_STATUSES:
            return
        if card.has(Status.STATUS_PROOF):
            return
        if status is Status.POISONED and card.has(Status.POISONED):
            self.destroy_at(loc, source)
            return
        opposite = {Status.BLEEDING: Status.GROWING, Status.GROWING: Status.BLEEDING}.get(status)
        other = card.entry(opposite) if opposite is not None else None
        if other is not None and opposite is not None and turns is not None:
            cancelled = min(turns, other.turns) if other.turns is not None else turns
            turns -= cancelled
            if other.turns is not None:
                other.turns -= cancelled
                if other.turns <= 0:
                    self.drop_status(loc, opposite, "cancelled", source)
                else:
                    self.emit(
                        "status_reduced",
                        seat=loc.seat,
                        instance=card.instance,
                        card=card.card,
                        status=opposite.value,
                        turns=other.turns,
                        reason=reason,
                        source=source,
                    )
            if turns <= 0:
                return
        existing = card.entry(status)
        if existing is not None:
            if existing.turns is None:
                return  # a status without a timer stays as it is
            existing.turns = None if turns is None else existing.turns + turns
            entry = existing
        else:
            entry = StatusEntry(status, turns)
            card.statuses.append(entry)
        self.emit(
            "status_added",
            seat=loc.seat,
            instance=card.instance,
            card=card.card,
            reason=reason,
            source=source,
            **_status_fields(entry),
        )
        self.sync_auras()
        self.check_destruction()

    def remove_statuses(
        self, iid: str, statuses: tuple[Status, ...] | None, source: str | None
    ) -> None:
        loc = self.loc(iid)
        if loc is None:
            return
        for entry in list(loc.card.statuses):
            if entry.status in AUTOMATIC_STATUSES:
                continue
            if statuses is None or entry.status in statuses:
                self.drop_status(loc, entry.status, "remove_statuses", source)
        self.check_destruction()

    def tick_statuses(self, seat: int) -> None:
        """At a player's turn end: ``bleeding`` and ``growing`` act, then every timer on the card
        drops by one and a status whose timer runs out is removed (§9, §11.4)."""
        for loc in [loc for loc in self.board() if loc.seat == seat]:
            iid = loc.card.instance
            if loc.card.has(Status.BLEEDING):
                self.damage(iid, 1, Status.BLEEDING.value, None, pierce_armor=True)
            current = self.loc(iid)
            if current is not None and current.card.has(Status.GROWING):
                self.boost(iid, 1, Status.GROWING.value, None)
            current = self.loc(iid)
            if current is not None:
                for entry in list(current.card.statuses):
                    if entry.turns is None:
                        continue
                    entry.turns -= 1
                    if entry.turns <= 0:
                        self.drop_status(current, entry.status, "expired", None)
            self.check_destruction()

    # --- row effects ---------------------------------------------------------------------------

    def act_row_effects(self, seat: int) -> None:
        """At a player's turn start, the per-turn row effects on their row-sides act, in the
        order they were set (§10, §11.4)."""
        sides = self.s.players[seat].rows
        order = sorted(
            (row for row in self.s.rules.rows if sides[row].effect is not None),
            key=lambda row: sides[row].effect.since,  # type: ignore[union-attr]
        )
        for row in order:
            effect = sides[row].effect
            if effect is None or effect.effect is RowEffectKind.DAMAGE_ON_ARRIVAL:
                continue
            units = [
                loc
                for loc in self.board()
                if loc.seat == seat and loc.row is row and self.is_unit(loc.card)
            ]
            kind = effect.effect
            if kind is RowEffectKind.DAMAGE_STRONGEST:
                targets = self.pick_extreme(units, strongest=True)
            elif kind is RowEffectKind.DAMAGE_WEAKEST:
                targets = self.pick_extreme(units, strongest=False)
            else:
                targets = self.pick_random(units, effect.count or 1)
            for loc in targets:
                if kind is RowEffectKind.BOOST_RANDOM:
                    self.boost(loc.card.instance, effect.amount, kind.value, None)
                else:
                    self.damage(loc.card.instance, effect.amount, kind.value, None)

    def row_sides(
        self,
        seat: int,
        acting: CardInstance | None,
        pick: RowPick,
        side: Side | None,
        rows: tuple[Row, ...] | None,
    ) -> list[tuple[int, Row]]:
        if pick is RowPick.THIS:
            loc = self.loc(acting.instance) if acting is not None else None
            return [(loc.seat, loc.row)] if loc is not None else []
        if pick is RowPick.CHOSEN:
            return []
        start = self.s.active
        return [
            (s, r)
            for s in (start, 1 - start)
            if s in _seats_for(self.s, seat, side)
            for r in self.s.rules.rows
            if rows is None or r in rows
        ]

    # --- zones ---------------------------------------------------------------------------------

    def draw(self, seat: int, count: int) -> int:
        """Draw ``count`` cards one at a time (§11.5). Returns how many were not drawn because
        the hand was full."""
        player = self.s.players[seat]
        full = empty = 0
        for _ in range(count):
            if len(player.hand) >= self.s.rules.hand_limit:
                full += 1
            elif not player.deck:
                empty += 1
            else:
                inst = player.deck.pop(0)
                player.hand.append(inst)
                self.emit("card_drawn", seat=seat, instance=inst.instance, card=inst.card)
        if full:
            self.emit("draw_skipped", seat=seat, reason="hand_full", count=full)
        if empty:
            self.emit("draw_skipped", seat=seat, reason="deck_empty", count=empty)
        return full

    def zone_candidates(
        self, zone: list[CardInstance], source: CardSource, acting: CardInstance | None
    ) -> list[CardInstance]:
        kinds = source.where.kind
        return [
            c
            for c in zone
            if (kinds is None or self.defn(c).kind in kinds)
            and self.where_ok(c, source.where, acting)
        ]

    def pick_cards(self, cands: list[CardInstance], source: CardSource) -> list[CardInstance]:
        """``first``, ``random`` and ``all`` of §7.3, in zone order; ``chosen`` is phase C."""
        if source.pick is CardPick.FIRST:
            return cands[: source.count or 1]
        if source.pick is CardPick.ALL:
            return cands if source.count is None else cands[: source.count]
        if source.pick is CardPick.RANDOM:
            pool = list(range(len(cands)))
            chosen: list[int] = []
            for _ in range(min(source.count or 1, len(pool))):
                chosen.append(pool.pop(self.rng.below(len(pool))))
            return [cands[i] for i in sorted(chosen)]
        return []

    def place_stratagem(self, seat: int, card_id: str) -> None:
        """ADR 0011: the round-one starter's stratagem starts on their side of the board, at the
        left end of the first row it allows, taking a place like any card. Nothing acts on it;
        its activated ability is ready from the first turn, and it stays until it is used."""
        card = self.new_instance(card_id, seat)
        row = _allowed_rows(self.s.rules, self.defn(card))[0]
        self.s.players[seat].rows[row].cards.insert(0, card)
        self.emit(
            "stratagem_placed",
            seat=seat,
            instance=card.instance,
            card=card.card,
            row=row.value,
            position=0,
        )

    # --- match flow ----------------------------------------------------------------------------

    def start_round(self) -> None:
        s = self.s
        s.phase = Phase.MULLIGAN
        s.turn = None
        s.active = s.starter
        self.emit("round_started", round=s.round, starter=s.starter)
        skipped = [0, 0]
        for seat in (s.starter, s.other(s.starter)):
            skipped[seat] = self.draw(seat, s.rules.draws(s.round))
        redraws = [
            s.rules.mulligans(s.round) + skipped[seat] * s.rules.mulligans_per_skipped_draw
            for seat in (0, 1)
        ]
        if s.round == 1:
            redraws[s.starter] += s.rules.starter_extra_mulligans  # ADR 0011
        for seat in (0, 1):
            s.players[seat].mulligan = MulliganState(remaining=redraws[seat])
        self.emit("mulligan_started", round=s.round, redraws=redraws)
        for seat in (s.starter, s.other(s.starter)):
            player = s.players[seat]
            if redraws[seat] <= 0 or not player.hand or not player.deck:
                self.finish_mulligan(seat)
        self.maybe_end_mulligan()

    def mulligan(self, seat: int, instance: str) -> None:
        """One redraw (§11.5): the card goes back, the first card from the top whose id this
        player has not returned in this mulligan replaces it, and the returned card is inserted
        into the deck at a position drawn with the seeded PRNG."""
        s = self.s
        if s.phase is not Phase.MULLIGAN:
            raise IllegalIntent("illegal_intent", "error.intent.not-mulligan-phase")
        player = s.players[seat]
        m = player.mulligan
        if m is None or m.done:
            raise IllegalIntent("illegal_intent", "error.mulligan.over")
        if m.remaining <= 0 or not player.deck:
            raise IllegalIntent("illegal_intent", "error.mulligan.none-left")
        returned = _hand_card(s, seat, instance)
        index = player.hand.index(returned)
        m.returned.append(returned.card)
        self.emit("card_redrawn", seat=seat, instance=returned.instance, card=returned.card)
        replacement = next((c for c in player.deck if c.card not in m.returned), player.deck[0])
        player.deck.remove(replacement)
        player.hand[index] = replacement
        self.emit("card_drawn", seat=seat, instance=replacement.instance, card=replacement.card)
        player.deck.insert(self.rng.below(len(player.deck) + 1), returned)
        m.remaining -= 1
        m.used += 1
        if m.remaining <= 0:
            self.finish_mulligan(seat)
        self.maybe_end_mulligan()

    def end_mulligan(self, seat: int) -> None:
        s = self.s
        if s.phase is not Phase.MULLIGAN:
            raise IllegalIntent("illegal_intent", "error.intent.not-mulligan-phase")
        m = s.players[seat].mulligan
        if m is None or m.done:
            raise IllegalIntent("illegal_intent", "error.mulligan.over")
        self.finish_mulligan(seat)
        self.maybe_end_mulligan()

    def finish_mulligan(self, seat: int) -> None:
        m = self.s.players[seat].mulligan
        assert m is not None
        m.done = True
        self.emit("mulligan_done", seat=seat, count=m.used)

    def maybe_end_mulligan(self) -> None:
        s = self.s
        if not all(p.mulligan is not None and p.mulligan.done for p in s.players):
            return
        for p in s.players:
            p.mulligan = None
        s.phase = Phase.PLAYING
        self.start_turn(s.starter)

    def start_turn(self, seat: int) -> None:
        """§11.4 steps 1 to 5: cooldowns drop; the ``on_turn_start`` abilities of the player's
        cards resolve; then the row effects on their row-sides act, in the order they were set;
        each step resolves with what it causes before the next."""
        s = self.s
        s.turn = s.active = seat
        self.emit("turn_started", seat=seat)
        player = s.players[seat]
        for loc in self.board():
            if loc.seat == seat and loc.card.cooldown > 0:
                loc.card.cooldown -= 1
        if player.leader is not None and player.leader.cooldown > 0:
            player.leader.cooldown -= 1
        self.fire_side(seat, Trigger.ON_TURN_START)
        self.settle_unasked()
        self.act_row_effects(seat)
        self.check_destruction()
        self.settle_unasked()
        if not player.hand and not self.any_order_ready(seat):
            self.do_pass(seat, auto=True)

    def any_order_ready(self, seat: int) -> bool:
        player = self.s.players[seat]
        cards = [loc.card for loc in self.board() if loc.seat == seat]
        if player.leader is not None:
            cards.append(player.leader)
        return any(order_ready(self.lib, self.s, seat, c) for c in cards)

    def do_pass(self, seat: int, auto: bool = False) -> None:
        player = self.s.players[seat]
        if player.passed:
            raise IllegalIntent("illegal_intent", "error.intent.already-passed")
        player.passed = True
        self.emit("player_passed", seat=seat, auto=auto)
        self.emit("turn_ended", seat=seat)
        self.next_turn(seat)

    def end_turn(self, seat: int) -> None:
        """§11.4 steps 6 and 7: the statuses of the player's cards act, then their
        ``on_turn_end`` abilities; each step resolves with what it causes before the next."""
        self.tick_statuses(seat)
        self.settle_unasked()
        self.fire_side(seat, Trigger.ON_TURN_END)
        self.settle_unasked()
        self.emit("turn_ended", seat=seat)
        self.next_turn(seat)

    def next_turn(self, seat: int) -> None:
        s = self.s
        other = s.other(seat)
        if not s.players[other].passed:
            self.start_turn(other)
        elif not s.players[seat].passed:
            self.start_turn(seat)
        else:
            self.end_round()

    def end_round(self) -> None:
        """§11.5 round end."""
        s = self.s
        s.turn = None
        for loc in self.board():
            self.fire(loc.card, Trigger.ON_ROUND_END, loc.seat)
        self.settle_unasked()
        scores = (score(self.lib, s, 0), score(self.lib, s, 1))
        if scores[0] != scores[1]:
            winners: tuple[int, ...] = (0,) if scores[0] > scores[1] else (1,)
        else:
            winners = (0, 1) if s.rules.tie_rule is TieRule.BOTH_WIN else ()
        for w in winners:
            s.players[w].rounds_won += 1
        s.rounds.append(RoundResult(s.round, winners, scores))
        self.emit("round_ended", round=s.round, winners=list(winners), scores=list(scores))
        kept: list[str] = []
        for loc in self.board():
            card = loc.card
            if card.has(Status.KEPT_AT_ROUND_END):
                kept.append(card.instance)
                continue
            self.s.players[loc.seat].rows[loc.row].cards.remove(card)
            banished = self.banished_on_leave(card)
            self.reset(card)
            owner = s.players[card.owner]
            (owner.banished if banished else owner.graveyard).append(card)
            if banished:
                self.emit("card_banished", seat=loc.seat, instance=card.instance, card=card.card)
        for p in s.players:
            for side in p.rows.values():
                side.effect = None
            p.passed = False
        self.emit("board_cleared", round=s.round, kept=kept)
        self.sync_auras()
        for iid in kept:
            kept_loc = self.loc(iid)
            if kept_loc is not None and kept_loc.card.has(Status.KEPT_AT_ROUND_END):
                self.drop_status(kept_loc, Status.KEPT_AT_ROUND_END, "kept", None)
        self.check_destruction()
        wins = [p.rounds_won for p in s.players]
        if max(wins) >= s.rules.rounds_to_win or s.round >= s.rules.max_rounds:
            s.phase = Phase.MATCH_OVER
            s.turn = None
            s.winner = None if wins[0] == wins[1] else (0 if wins[0] > wins[1] else 1)
            self.emit(
                "match_ended",
                winner=s.winner,
                rounds=[
                    {"round": r.round, "winners": list(r.winners), "scores": list(r.scores)}
                    for r in s.rounds
                ],
            )
            return
        s.starter = self.next_starter(winners)
        s.round += 1
        self.start_round()

    def next_starter(self, winners: tuple[int, ...]) -> int:
        s = self.s
        rule = s.rules.next_round_starter
        if rule is NextRoundStarter.ALTERNATE or len(winners) != 1:
            return s.other(s.starter)
        return winners[0] if rule is NextRoundStarter.ROUND_WINNER else s.other(winners[0])

    # --- player actions ------------------------------------------------------------------------

    def play_card(self, seat: int, iid: str, row: Row | None, position: int | None) -> None:
        s = self.s
        player = s.players[seat]
        inst = _hand_card(s, seat, iid)
        defn = self.defn(inst)
        if defn.placed:
            if row is None:
                raise IllegalIntent("illegal_intent", "error.play.row-required")
            if row not in _allowed_rows(s.rules, defn):
                raise IllegalIntent("illegal_intent", "error.play.row-not-allowed")
            land = _landing_seat(s, seat, defn)
            side = s.players[land].rows[row]
            if len(side.cards) >= s.rules.row_capacity:
                raise IllegalIntent("illegal_intent", "error.play.row-full")
            if position is None:
                raise IllegalIntent("illegal_intent", "error.play.position-required")
            if not 0 <= position <= len(side.cards):
                raise IllegalIntent("illegal_intent", "error.play.position-out-of-range")
            player.hand.remove(inst)
            self.enter(inst, land, row, position)
            self.emit(
                "card_played",
                seat=seat,
                instance=inst.instance,
                card=inst.card,
                **{"from": "hand"},
                row=row.value,
                position=position,
                side="self" if land == seat else "opponent",
            )
            self.sync_auras()
            self.arrive(inst)
            self.check_destruction()
        elif defn.kind is Kind.SPECIAL:
            if row is not None or position is not None:
                raise IllegalIntent("illegal_intent", "error.play.row-not-allowed")
            player.hand.remove(inst)
            s.resolving.append(inst)
            self.emit(
                "card_played", seat=seat, instance=inst.instance, card=inst.card, **{"from": "hand"}
            )
        else:
            raise IllegalIntent("illegal_intent", "error.play.not-playable")
        self.fire(inst, Trigger.ON_PLAY, seat, row=row)
        if defn.placed:
            self.fire_ally_played(inst, seat)
        self.may_ask = True
        if not self.settle():
            self.finish_play(seat)

    def finish_play(self, seat: int) -> None:
        """After a played card and everything it caused resolved: specials go to their owner's
        graveyard, and the turn ends."""
        for special in list(self.s.resolving):
            self.s.resolving.remove(special)
            self.reset(special)
            self.s.players[special.owner].graveyard.append(special)
        self.end_turn(seat)

    def use_order(self, seat: int, iid: str) -> None:
        """§6.3: queue the card's ``on_activate`` abilities; the turn goes on afterwards. Only a
        stratagem is ever ready before phase C (``order_ready``)."""
        s = self.s
        loc = self.loc(iid)
        leader = s.players[seat].leader
        if (loc is None or loc.seat != seat) and (leader is None or leader.instance != iid):
            raise IllegalIntent("unknown_instance", iid)
        card = loc.card if loc is not None else leader
        assert card is not None
        if not order_ready(self.lib, s, seat, card):
            raise IllegalIntent("illegal_intent", "error.order.not-ready")
        self.order, self.order_started = card.instance, False
        self.may_ask = True
        self.fire(card, Trigger.ON_ACTIVATE, seat)
        self.settle()

    def start_order(self, iid: str) -> None:
        """The order's first ability starts to act: a charge is spent and the cooldown starts."""
        card = self.card_by_id(iid)
        if card is None:
            return
        activation = self.defn(card).activation
        if card.charges is not None:
            card.charges -= 1
        card.cooldown = activation.cooldown if activation is not None else 0
        loc = self.loc(iid)
        self.emit(
            "order_used",
            seat=loc.seat if loc is not None else card.owner,
            instance=iid,
            card=card.card,
            charges=card.charges,
            cooldown=card.cooldown,
        )

    def finish_order(self, iid: str, started: bool) -> None:
        """After an order resolved — its charge spent now if none of its abilities acted: a
        stratagem, used once, leaves the board for its owner's banished zone (ADR 0011)."""
        if not started:
            self.start_order(iid)
        loc = self.loc(iid)
        if loc is None or self.defn(loc.card).kind is not Kind.STRATAGEM:
            return
        card = loc.card
        self.s.players[loc.seat].rows[loc.row].cards.remove(card)
        self.reset(card)
        self.s.players[card.owner].banished.append(card)
        self.emit("card_banished", seat=loc.seat, instance=card.instance, card=card.card)
        self.sync_auras()
        self.check_destruction()

    def choose(self, seat: int, option: int) -> None:
        s = self.s
        pending = s.pending
        if s.phase is not Phase.CHOOSING or pending is None:
            raise IllegalIntent("illegal_intent", "error.choice.none-pending")
        if pending.seat != seat:
            raise IllegalIntent("not_your_turn")
        if not 0 <= option < len(pending.options):
            raise IllegalIntent("illegal_intent", "error.choice.out-of-range")
        s.pending = None
        s.phase = Phase.PLAYING
        self.emit("choice_made", seat=seat, option=option)
        self.queue = pending.queue
        self.order, self.order_started = pending.order, pending.order_started
        self.may_ask = True
        inv = pending.invocation
        ability = self.ability(inv)
        acting = self.acting_card(inv)
        target = self.loc(pending.options[option])
        targets = [target] if target is not None else []
        self.start_pending_order()
        self.perform(inv, acting, ability, targets)
        self.hand_on(inv, targets)
        if self.settle() or pending.order is not None:
            return
        assert s.turn is not None
        self.finish_play(s.turn)

    def cancel_choice(self, seat: int) -> None:
        pending = self.s.pending
        if self.s.phase is not Phase.CHOOSING or pending is None:
            raise IllegalIntent("illegal_intent", "error.choice.none-pending")
        if pending.seat != seat:
            raise IllegalIntent("not_your_turn")
        if not pending.cancellable:
            raise IllegalIntent("illegal_intent", "error.choice.not-cancellable")
        # nothing has happened since the use_order: the match is back where it was
        self.s.pending = None
        self.s.phase = Phase.PLAYING
        self.emit("choice_cancelled", seat=seat)

    # --- resolution ----------------------------------------------------------------------------

    def ability(self, inv: Invocation) -> Ability:
        return self.lib[inv.card].abilities[inv.ability_index]

    def acting_card(self, inv: Invocation) -> CardInstance | None:
        """The card an invocation belongs to: on the board, resolving as a special, a leader, or
        anywhere else it went."""
        return self.card_by_id(inv.instance)

    def card_by_id(self, iid: str) -> CardInstance | None:
        loc = self.loc(iid)
        if loc is not None:
            return loc.card
        for c in self.all_cards():
            if c.instance == iid:
                return c
        return None

    def fire(
        self,
        card: CardInstance,
        when: Trigger,
        seat: int,
        row: Row | None = None,
        trigger: str | None = None,
    ) -> None:
        """Queue the card's abilities with this trigger, in the order written, on behalf of
        ``seat`` (§6, §11.3)."""
        for i in self.defn(card).triggered(when):
            self.queue.append(Invocation(card.instance, card.card, i, seat, row, trigger))

    def fire_side(self, seat: int, when: Trigger) -> None:
        """Queue a trigger of every card on ``seat``'s side, in board order."""
        for loc in self.board():
            if loc.seat == seat:
                self.fire(loc.card, when, seat)

    def fire_ally_played(self, played: CardInstance, seat: int) -> None:
        """``on_ally_played`` of the other cards on the side a unit ``seat`` played landed on —
        when that is ``seat``'s own side (§6.1) — in board order."""
        here = self.loc(played.instance)
        if here is None or here.seat != seat or not self.is_unit(played):
            return
        for loc in self.board():
            if loc.seat == seat and loc.card is not played:
                self.fire(loc.card, Trigger.ON_ALLY_PLAYED, seat, trigger=played.instance)

    def hand_on(self, inv: Invocation, targets: list[Loc]) -> None:
        """Give what an ability acted on to the ability after it — the next queued one of the same
        card and trigger — for ``previous_targets`` (§7.1)."""
        when = self.ability(inv).when
        for nxt in self.queue:
            if (
                nxt.instance == inv.instance
                and nxt.ability_index > inv.ability_index
                and self.ability(nxt).when is when
            ):
                nxt.previous = [loc.card.instance for loc in targets]
                return

    def start_pending_order(self) -> None:
        """The resolving activated ability's first ability starts to act: its charge is spent."""
        if self.order is not None and not self.order_started:
            self.start_order(self.order)
            self.order_started = True

    def settle(self) -> bool:
        """Resolve the queue; once it is empty, finish the activated ability that filled it.
        True when a choice paused it."""
        self.resolved = 0
        while True:
            if self.run():
                return True
            if self.order is None:
                return False
            order, started = self.order, self.order_started
            self.order, self.order_started = None, True
            self.finish_order(order, started)

    def settle_unasked(self) -> None:
        """Resolve what a turn start, a turn end or a round end queued. Nothing there asks a
        player (the schema keeps choices to ``on_play`` and ``on_activate``), so nothing pauses."""
        self.may_ask = False
        paused = self.settle()
        assert not paused

    def run(self) -> bool:
        """Run the queue first in, first out (§11.3). True when paused for a choice; the rest of
        the queue then waits in the pending choice."""
        s = self.s
        while self.queue:
            if self.resolved >= QUEUE_STEPS_MAX:
                self.queue.clear()  # content that keeps triggering itself stops here
                return False
            self.resolved += 1
            inv = self.queue.pop(0)
            ability = self.ability(inv)
            acting = self.acting_card(inv)
            if not self.may_fire(inv, acting, ability):
                self.hand_on(inv, [])
                continue
            t = ability.target
            if t is not None and t.units is Units.CHOSEN:
                options = self.unit_candidates(inv.seat, acting, t, ability.do)
                if not options or not self.may_ask:
                    self.hand_on(inv, [])
                    continue
                pending = PendingChoice(
                    seat=inv.seat,
                    kind=ChoiceKind.UNIT,
                    invocation=inv,
                    prompt_key="choice." + ability.do.value.replace("_", "-"),
                    options=[loc.card.instance for loc in options],
                    queue=self.queue,
                    cancellable=self.order is not None and not self.order_started,
                    order=self.order,
                    order_started=self.order_started,
                )
                self.queue = []
                self.order, self.order_started = None, True
                s.pending = pending
                s.phase = Phase.CHOOSING
                self.emit(
                    "choice_requested",
                    seat=inv.seat,
                    kind=pending.kind.value,
                    prompt_key=pending.prompt_key,
                    option_count=len(pending.options),
                    source=inv.instance,
                    cancellable=pending.cancellable,
                )
                return True
            self.start_pending_order()
            targets = self.select_units(inv, acting, t, ability.do) if t is not None else []
            self.perform(inv, acting, ability, targets)
            self.hand_on(inv, targets)
        return False

    def may_fire(self, inv: Invocation, acting: CardInstance | None, a: Ability) -> bool:
        """§11.3: skipped when the card is locked, when it must be on the board and is not — every
        ability but ``on_destroyed`` and a special's ``on_play`` — or when its conditions fail.
        Words still waiting for the rest of phase C are skipped too."""
        if acting is None or a.do in PHASE_C_ACTIONS:
            return False
        if a.row_target is not None and a.row_target.pick is RowPick.CHOSEN:
            return False
        if a.cards is not None and a.cards.pick is CardPick.CHOSEN:
            return False
        loc = self.loc(acting.instance)
        off_board = a.when is Trigger.ON_DESTROYED or (
            self.defn(acting).kind is Kind.SPECIAL and a.when is Trigger.ON_PLAY
        )
        if not off_board and loc is None:
            return False
        if loc is not None and acting.has(Status.LOCKED):
            return False
        return self.conditions_hold(inv, acting, a.cond)

    def perform(
        self, inv: Invocation, acting: CardInstance | None, a: Ability, targets: list[Loc]
    ) -> None:
        """Carry out one ability on its targets, one at a time in board order (§8)."""
        seat, src = inv.seat, inv.instance
        ids = [loc.card.instance for loc in targets]
        do = a.do
        for iid in ids if do in _PER_TARGET else ():
            if do is Action.DAMAGE:
                self.damage(iid, a.amount, do.value, src)
            elif do is Action.BOOST:
                self.boost(iid, a.amount, do.value, src)
            elif do is Action.ADD_ARMOR:
                self.add_armor(iid, a.amount, src)
            elif do is Action.HEAL:
                self.heal(iid, src)
            elif do is Action.RESET_POWER:
                self.reset_power(iid, src)
            elif do is Action.RAISE_BASE_POWER:
                self.raise_base_power(iid, a.amount, src)
            elif do is Action.DESTROY:
                self.destroy(iid, src)
            elif do is Action.BANISH:
                self.banish(iid, src)
            elif do is Action.ADD_STATUS and a.status is not None:
                self.add_status(iid, a.status, a.turns, do.value, src)
            elif do is Action.REMOVE_STATUSES:
                self.remove_statuses(iid, a.statuses, src)
            elif do is Action.MOVE_TO_OTHER_ROW:
                self.move_to_other_row(iid)
            elif do is Action.RETURN_TO_HAND:
                self.return_to_hand(iid, src)
            elif do is Action.TAKE_CONTROL:
                self.take_control(iid, seat, src)
            elif do is Action.DRAIN:
                self.drain(acting, iid, a.amount, src)
            elif do is Action.DUEL:
                self.duel(acting, iid, src)
            elif do is Action.CONSUME:
                self.consume(acting, iid, src)
        if do is Action.DISCARD and a.cards is not None:
            self.discard(seat, acting, a.cards)
        elif do is Action.DRAW:
            self.draw(self.side_seat(seat, a.side), a.count or 1)
        elif do is Action.SUMMON_FROM_DECK and a.cards is not None:
            self.summon_from_deck(inv, acting, a)
        elif do is Action.PLACE_NEW_CARD:
            self.place_new_card(inv, acting, a)
        elif do is Action.SET_ROW_EFFECT:
            self.set_row_effect(seat, acting, a, src)
        elif do is Action.CLEAR_ROW_EFFECT:
            self.clear_row_effect(seat, acting, a, src)
        # continuous_boost acts through power (§11.1)

    def side_seat(self, seat: int, side: Side) -> int:
        return self.s.other(seat) if side is Side.OPPONENT else seat

    def drain(self, acting: CardInstance | None, iid: str, amount: int, source: str) -> None:
        """Damage the target; the acting unit is boosted by the damage that reached its power."""
        dealt = self.damage(iid, amount, Action.DRAIN.value, source)
        if acting is not None and dealt > 0 and self.loc(acting.instance) is not None:
            self.boost(acting.instance, dealt, Action.DRAIN.value, source)

    def duel(self, acting: CardInstance | None, iid: str, source: str) -> None:
        """The acting unit and the target damage each other by their power in turn, the acting
        unit first, until one of them has left the board."""
        if acting is None:
            return
        attacker, defender = acting.instance, iid
        for _ in range(DUEL_STRIKES_MAX):
            a_loc, d_loc = self.loc(attacker), self.loc(defender)
            if a_loc is None or d_loc is None:
                return
            if not self.is_unit(a_loc.card) or not self.is_unit(d_loc.card):
                return
            self.damage(defender, self.power(a_loc), Action.DUEL.value, source)
            attacker, defender = defender, attacker

    def consume(self, acting: CardInstance | None, iid: str, source: str) -> None:
        """Destroy the target; the acting unit is boosted by the target's power."""
        loc = self.loc(iid)
        if loc is None or not self.is_unit(loc.card):
            return
        gained = max(self.power(loc), 0)
        self.destroy_at(loc, source)
        if acting is not None and self.loc(acting.instance) is not None:
            self.boost(acting.instance, gained, Action.CONSUME.value, source)

    def discard(self, seat: int, acting: CardInstance | None, source: CardSource) -> None:
        owner_seat = self.side_seat(seat, source.side)
        hand = self.s.players[owner_seat].hand
        for card in self.pick_cards(self.zone_candidates(hand, source, acting), source):
            hand.remove(card)
            self.s.players[card.owner].graveyard.append(card)
            self.emit("card_discarded", seat=owner_seat, instance=card.instance, card=card.card)

    def summon_from_deck(self, inv: Invocation, acting: CardInstance | None, a: Ability) -> None:
        seat = inv.seat
        source = a.cards
        assert source is not None
        deck = self.s.players[self.side_seat(seat, source.side)].deck
        cands = [c for c in self.zone_candidates(deck, source, acting) if self.defn(c).placed]
        last: CardInstance | None = None
        for card in self.pick_cards(cands, source):
            land = _landing_seat(self.s, seat, self.defn(card))
            where = self.placement(card, land, acting, a.row, last, inv.row)
            if where is None or card not in deck:
                continue
            deck.remove(card)
            self.summon(card, land, where, seat, "deck")
            last = card

    def place_new_card(self, inv: Invocation, acting: CardInstance | None, a: Ability) -> None:
        seat = inv.seat
        if a.card is None or a.card not in self.lib or not self.lib[a.card].placed:
            return
        land = self.side_seat(seat, a.side)
        last: CardInstance | None = None
        for _ in range(a.count or 1):
            probe = CardInstance("", a.card, seat)
            where = self.placement(probe, land, acting, a.row, last, inv.row)
            if where is None:
                return
            card = self.new_instance(a.card, seat)
            self.summon(card, land, where, seat, "created", (Status.BANISH_ON_LEAVE,))
            last = card

    def set_row_effect(
        self, seat: int, acting: CardInstance | None, a: Ability, source: str
    ) -> None:
        rt = a.row_target
        if rt is None or a.effect is None:
            return
        for side_seat, row in self.row_sides(seat, acting, rt.pick, rt.side, rt.rows):
            fields: dict[str, Any] = {"effect": a.effect.value, "amount": a.amount}
            if a.count is not None:
                fields["count"] = a.count
            self.emit("row_effect_set", seat=side_seat, row=row.value, source=source, **fields)
            since = self.s.seq  # the event's own seq: later effects act later
            self.s.players[side_seat].rows[row].effect = RowEffect(
                a.effect, a.amount, a.count, since
            )

    def clear_row_effect(
        self, seat: int, acting: CardInstance | None, a: Ability, source: str
    ) -> None:
        rt = a.row_target
        if rt is None:
            return
        for side_seat, row in self.row_sides(seat, acting, rt.pick, rt.side, rt.rows):
            side = self.s.players[side_seat].rows[row]
            effect = side.effect
            if effect is None or (
                a.only is not None and row_effect_class(effect.effect) is not a.only
            ):
                continue
            side.effect = None
            self.emit(
                "row_effect_cleared",
                seat=side_seat,
                row=row.value,
                effect=effect.effect.value,
                source=source,
            )


# Actions that act on each target of a unit selector in turn.
_PER_TARGET = frozenset(
    {
        Action.DAMAGE,
        Action.BOOST,
        Action.ADD_ARMOR,
        Action.HEAL,
        Action.RESET_POWER,
        Action.RAISE_BASE_POWER,
        Action.DESTROY,
        Action.BANISH,
        Action.ADD_STATUS,
        Action.REMOVE_STATUSES,
        Action.MOVE_TO_OTHER_ROW,
        Action.RETURN_TO_HAND,
        Action.TAKE_CONTROL,
        Action.DRAIN,
        Action.DUEL,
        Action.CONSUME,
    }
)
