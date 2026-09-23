"""The rules engine: ``new_match``, ``apply`` and ``legal_intents``.

``apply`` never mutates its input; it deep-copies the state, applies one intent and returns the
new state with the events it produced. Everything that changes a match goes through it.
"""

from __future__ import annotations

import copy
from typing import Any

from .events import Event
from .intents import Choose, Intent, Mulligan, Pass, PlayCard, UseLeader
from .model import (
    DEFAULT_RULES,
    PASSIVE_ACTIONS,
    ROWS,
    Ability,
    Action,
    CardDef,
    CardInstance,
    Deck,
    Invocation,
    Kind,
    Library,
    MatchState,
    PendingChoice,
    Phase,
    PlayerState,
    RoundResult,
    Row,
    RowState,
    Rules,
    Side,
    Target,
    Trigger,
    Units,
    Where,
)
from .power import board_powers, effective_power, row_total, score
from .rng import Pcg32


class IllegalIntent(Exception):
    """The intent is not acceptable in this state. ``code`` follows docs/protocol/match.md §10."""

    def __init__(self, code: str, reason: str = "") -> None:
        super().__init__(f"{code}: {reason}" if reason else code)
        self.code = code
        self.reason = reason


NEUTRAL = "neutral"


def check_deck(lib: Library, deck: Deck, rules: Rules) -> list[str]:
    """Problems with a deck as message keys; empty when the deck is legal."""
    problems: list[str] = []
    units = specials = 0
    for cid in deck.cards:
        defn = lib.get(cid)
        if defn is None:
            problems.append(f"error.deck.unknown-card:{cid}")
            continue
        if defn.faction not in (deck.faction, NEUTRAL):
            problems.append(f"error.deck.wrong-faction:{cid}")
        if defn.kind is Kind.UNIT:
            units += 1
        elif defn.kind is Kind.SPECIAL:
            specials += 1
        else:
            problems.append(f"error.deck.leader-in-deck:{cid}")
    if units < rules.min_units:
        problems.append("error.deck.too-few-units")
    if specials > rules.max_specials:
        problems.append("error.deck.too-many-specials")
    if deck.leader is not None:
        leader = lib.get(deck.leader)
        if leader is None:
            problems.append(f"error.deck.unknown-card:{deck.leader}")
        elif leader.kind is not Kind.LEADER:
            problems.append(f"error.deck.leader-not-leader:{deck.leader}")
        elif leader.faction not in (deck.faction, NEUTRAL):
            problems.append(f"error.deck.wrong-faction:{deck.leader}")
    return problems


def new_match(
    lib: Library, decks: tuple[Deck, Deck], seed: int, rules: Rules = DEFAULT_RULES
) -> tuple[MatchState, list[Event]]:
    """Shuffle, decide who starts, deal the opening hands and enter the mulligan phase."""
    for seat, deck in enumerate(decks):
        problems = check_deck(lib, deck, rules)
        if problems:
            raise ValueError(f"deck for seat {seat} is not legal: {', '.join(problems)}")
    rng = Pcg32(seed)
    state = MatchState(
        rules=rules,
        seed=seed,
        rng_state=rng.state,
        rng_inc=rng.inc,
        phase=Phase.MULLIGAN,
        round=1,
        starter=0,
        turn=None,
        mulligan_seat=None,
        players=[],
        next_instance=1,
        seq=0,
        winner=None,
        pending=None,
        resolving=[],
        rounds=[],
    )
    ctx = _Ctx(lib, state, [])
    for seat, deck in enumerate(decks):
        cards = [ctx.new_instance(cid, seat) for cid in deck.cards]
        ctx.rng.shuffle(cards)
        leader = ctx.new_instance(deck.leader, seat) if deck.leader is not None else None
        state.players.append(
            PlayerState(
                seat=seat,
                faction=deck.faction,
                deck=cards,
                hand=[],
                discard=[],
                rows={row: RowState() for row in ROWS},
                leader=leader,
                lives=rules.lives,
            )
        )
    state.starter = ctx.rng.below(2)
    ctx.emit("match_started", starter=state.starter, seed=seed)
    for seat in (state.starter, state.other(state.starter)):
        ctx.draw(seat, rules.hand_size)
    state.mulligan_seat = state.starter
    ctx.emit("mulligan_started", seat=state.starter, max=rules.mulligan_max)
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
    new = copy.deepcopy(state)
    ctx = _Ctx(lib, new, [])
    if isinstance(intent, Mulligan):
        ctx.mulligan(seat, intent.cards)
    elif isinstance(intent, Choose):
        ctx.choose(seat, intent.option)
    else:
        if new.phase is Phase.MULLIGAN:
            raise IllegalIntent("illegal_intent", "error.intent.mulligan-phase")
        if new.phase is Phase.CHOOSING:
            raise IllegalIntent("choice_pending")
        if new.turn != seat:
            raise IllegalIntent("not_your_turn")
        if isinstance(intent, PlayCard):
            ctx.play_card(seat, intent.card, intent.row)
        elif isinstance(intent, UseLeader):
            ctx.use_leader(seat)
        elif isinstance(intent, Pass):
            ctx.do_pass(seat)
        else:
            raise IllegalIntent("illegal_intent", "error.intent.unknown")
    ctx.save_rng()
    return new, ctx.events


def legal_intents(lib: Library, state: MatchState, seat: int) -> list[Intent]:
    """Exactly the intents ``apply`` would accept from ``seat`` right now.

    During the mulligan the single ``Mulligan()`` entry stands for any subset of the hand up to
    ``rules.mulligan_max`` cards.
    """
    if state.phase is Phase.MATCH_OVER:
        return []
    if state.phase is Phase.MULLIGAN:
        return [Mulligan()] if state.mulligan_seat == seat else []
    if state.phase is Phase.CHOOSING:
        pending = state.pending
        if pending is None or pending.seat != seat:
            return []
        return [Choose(i) for i in range(len(pending.options))]
    if state.turn != seat:
        return []
    player = state.players[seat]
    out: list[Intent] = [Pass()]
    for inst in player.hand:
        defn = lib[inst.card]
        if defn.kind is Kind.UNIT:
            out.extend(PlayCard(inst.instance, row) for row in defn.rows)
        elif defn.kind is Kind.SPECIAL:
            out.append(PlayCard(inst.instance, None))
    if player.leader is not None and not player.leader_used:
        out.append(UseLeader())
    return out


class _Ctx:
    """One application of one intent: the state being mutated, its RNG and the events so far."""

    def __init__(self, lib: Library, state: MatchState, events: list[Event]) -> None:
        self.lib = lib
        self.s = state
        self.events = events
        self.rng = Pcg32.from_state(state.rng_state, state.rng_inc)

    # --- plumbing ------------------------------------------------------------------------------

    def save_rng(self) -> None:
        self.s.rng_state = self.rng.state
        self.s.rng_inc = self.rng.inc

    def emit(self, type_: str, **data: Any) -> None:
        self.s.seq += 1
        self.events.append(Event(self.s.seq, type_, data))

    def new_instance(self, card_id: str, owner: int) -> CardInstance:
        inst = CardInstance(f"c{self.s.next_instance}", card_id, owner, self.lib[card_id].power)
        self.s.next_instance += 1
        return inst

    def defn(self, inst: CardInstance) -> CardDef:
        return self.lib[inst.card]

    def seats_for(self, seat: int, side: Side) -> list[int]:
        if side is Side.SELF:
            return [seat]
        if side is Side.OPPONENT:
            return [self.s.other(seat)]
        return [seat, self.s.other(seat)]

    def side_seat(self, seat: int, side: Side) -> int:
        return self.s.other(seat) if side is Side.OPPONENT else seat

    # --- zones ---------------------------------------------------------------------------------

    def hand_card(self, seat: int, instance_id: str) -> CardInstance | None:
        for inst in self.s.players[seat].hand:
            if inst.instance == instance_id:
                return inst
        return None

    def board_units(self) -> list[tuple[int, Row, CardInstance]]:
        out: list[tuple[int, Row, CardInstance]] = []
        for seat in (0, 1):
            for row in ROWS:
                out.extend((seat, row, u) for u in self.s.players[seat].rows[row].units)
        return out

    def locate(self, instance_id: str) -> tuple[int, Row, int] | None:
        for seat in (0, 1):
            for row in ROWS:
                for index, u in enumerate(self.s.players[seat].rows[row].units):
                    if u.instance == instance_id:
                        return seat, row, index
        return None

    def find_instance(self, instance_id: str) -> CardInstance | None:
        """A card that can still act: on the board, resolving as a special, or a leader."""
        for _, _, u in self.board_units():
            if u.instance == instance_id:
                return u
        for u in self.s.resolving:
            if u.instance == instance_id:
                return u
        for p in self.s.players:
            if p.leader is not None and p.leader.instance == instance_id:
                return p.leader
        return None

    def place(self, unit: CardInstance, seat: int, row: Row) -> None:
        self.s.players[seat].rows[row].units.append(unit)

    def draw(self, seat: int, count: int) -> None:
        player = self.s.players[seat]
        for _ in range(count):
            if not player.deck:
                return
            inst = player.deck.pop(0)
            player.hand.append(inst)
            self.emit("card_drawn", seat=seat, instance=inst.instance, card=inst.card)

    # --- match flow ----------------------------------------------------------------------------

    def mulligan(self, seat: int, cards: tuple[str, ...]) -> None:
        s = self.s
        if s.phase is not Phase.MULLIGAN:
            raise IllegalIntent("illegal_intent", "error.intent.not-mulligan-phase")
        if s.mulligan_seat != seat:
            raise IllegalIntent("not_your_turn")
        if len(cards) > s.rules.mulligan_max:
            raise IllegalIntent("illegal_intent", "error.mulligan.too-many")
        if len(set(cards)) != len(cards):
            raise IllegalIntent("illegal_intent", "error.mulligan.duplicate")
        player = s.players[seat]
        chosen: list[CardInstance] = []
        for cid in cards:
            inst = self.hand_card(seat, cid)
            if inst is None:
                raise IllegalIntent("unknown_instance", cid)
            chosen.append(inst)
        for inst in chosen:
            player.hand.remove(inst)
        self.draw(seat, len(chosen))
        if chosen:
            player.deck.extend(chosen)
            self.rng.shuffle(player.deck)
        player.mulligan_done = True
        self.emit("mulligan_done", seat=seat, count=len(chosen))
        other = s.other(seat)
        if not s.players[other].mulligan_done:
            s.mulligan_seat = other
            self.emit("mulligan_started", seat=other, max=s.rules.mulligan_max)
            return
        s.mulligan_seat = None
        s.phase = Phase.PLAYING
        self.emit("round_started", round=s.round, starter=s.starter)
        self.start_turn(s.starter)

    def start_turn(self, seat: int) -> None:
        s = self.s
        s.turn = seat
        self.emit("turn_started", seat=seat)
        queue = [
            Invocation(u.instance, u.card, i, seat)
            for _, _, u in self.board_units()
            if u.owner == seat
            for i in self.defn(u).triggered(Trigger.TURN_START)
        ]
        if queue:
            self.resolve(queue, allow_choice=False)
        player = s.players[seat]
        if not player.hand and (player.leader is None or player.leader_used):
            self.do_pass(seat, auto=True)

    def do_pass(self, seat: int, auto: bool = False) -> None:
        s = self.s
        player = s.players[seat]
        if player.passed:
            raise IllegalIntent("illegal_intent", "error.intent.already-passed")
        player.passed = True
        self.emit("player_passed", seat=seat, auto=auto)
        other = s.other(seat)
        if s.players[other].passed:
            self.end_round()
        else:
            self.start_turn(other)

    def end_turn(self, seat: int) -> None:
        s = self.s
        other = s.other(seat)
        if not s.players[other].passed:
            self.start_turn(other)
        elif not s.players[seat].passed:
            self.start_turn(seat)
        else:
            self.end_round()

    def finish_action(self, seat: int) -> None:
        """After a card's abilities resolved: discard specials that did not stay on the board."""
        s = self.s
        for special in list(s.resolving):
            s.resolving.remove(special)
            if self.locate(special.instance) is None:
                s.players[special.owner].discard.append(special)
        self.end_turn(seat)

    def end_round(self) -> None:
        s = self.s
        queue = [
            Invocation(u.instance, u.card, i, u.owner)
            for _, _, u in self.board_units()
            for i in self.defn(u).triggered(Trigger.ROUND_END)
        ]
        if queue:
            self.resolve(queue, allow_choice=False)
        scores = (score(self.lib, s, 0), score(self.lib, s, 1))
        if scores[0] > scores[1]:
            winner: int | None = 0
        elif scores[1] > scores[0]:
            winner = 1
        else:
            winner = None
        s.rounds.append(RoundResult(s.round, winner, scores))
        if winner is None:
            for p in s.players:
                p.lives -= 1
        else:
            s.players[s.other(winner)].lives -= 1
            s.players[winner].rounds_won += 1
        self.emit("round_ended", round=s.round, winner=winner, scores=list(scores))
        for p in s.players:
            for row in ROWS:
                row_state = p.rows[row]
                p.discard.extend(row_state.units)
                row_state.units = []
                row_state.effects = []
            p.passed = False
        self.emit("board_cleared", round=s.round)
        alive = [p.seat for p in s.players if p.lives > 0]
        if len(alive) < 2:
            s.phase = Phase.MATCH_OVER
            s.turn = None
            s.winner = alive[0] if len(alive) == 1 else None
            self.emit(
                "match_ended",
                winner=s.winner,
                rounds=[
                    {"round": r.round, "winner": r.winner, "scores": list(r.scores)}
                    for r in s.rounds
                ],
            )
            return
        s.round += 1
        s.starter = winner if winner is not None else s.other(s.starter)
        self.emit("round_started", round=s.round, starter=s.starter)
        self.start_turn(s.starter)

    # --- player actions ------------------------------------------------------------------------

    def play_card(self, seat: int, instance_id: str, row: Row | None) -> None:
        s = self.s
        player = s.players[seat]
        inst = self.hand_card(seat, instance_id)
        if inst is None:
            raise IllegalIntent("unknown_instance", instance_id)
        defn = self.defn(inst)
        if defn.kind is Kind.UNIT:
            if row is None:
                if len(defn.rows) != 1:
                    raise IllegalIntent("illegal_intent", "error.play.row-required")
                row = defn.rows[0]
            elif row not in defn.rows:
                raise IllegalIntent("illegal_intent", "error.play.row-not-allowed")
            player.hand.remove(inst)
            self.place(inst, self.side_seat(seat, defn.deploy), row)
            self.emit(
                "card_played",
                seat=seat,
                instance=inst.instance,
                card=inst.card,
                row=row.value,
                side=defn.deploy.value,
            )
        elif defn.kind is Kind.SPECIAL:
            if row is not None:
                raise IllegalIntent("illegal_intent", "error.play.row-not-allowed")
            player.hand.remove(inst)
            s.resolving.append(inst)
            self.emit("card_played", seat=seat, instance=inst.instance, card=inst.card, side="self")
        else:
            raise IllegalIntent("illegal_intent", "error.play.not-playable")
        queue = [
            Invocation(inst.instance, inst.card, i, seat) for i in defn.triggered(Trigger.PLAYED)
        ]
        if not self.resolve(queue, allow_choice=True):
            self.finish_action(seat)

    def use_leader(self, seat: int) -> None:
        player = self.s.players[seat]
        leader = player.leader
        if leader is None or player.leader_used:
            raise IllegalIntent("illegal_intent", "error.leader.unavailable")
        player.leader_used = True
        self.emit("leader_used", seat=seat, card=leader.card)
        queue = [
            Invocation(leader.instance, leader.card, i, seat)
            for i in self.defn(leader).triggered(Trigger.ACTIVATED)
        ]
        if not self.resolve(queue, allow_choice=True):
            self.finish_action(seat)

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
        ability = self.ability_of(pending.invocation)
        before = board_powers(self.lib, s)
        new = self.apply_choice(pending.invocation, ability, pending.options[option])
        self.emit_power_changes(before, ability.do.value)
        if not self.resolve(pending.queue + new, allow_choice=True):
            self.finish_action(seat)

    # --- ability resolution --------------------------------------------------------------------

    def ability_of(self, inv: Invocation) -> Ability:
        return self.lib[inv.card].abilities[inv.ability_index]

    def resolve(self, queue: list[Invocation], allow_choice: bool) -> bool:
        """Run invocations in order. Returns True when stopped for a player's choice."""
        s = self.s
        while queue:
            inv = queue.pop(0)
            ability = self.ability_of(inv)
            if ability.do in PASSIVE_ACTIONS:
                continue
            inst = self.find_instance(inv.instance)
            if inst is None:
                continue
            before = board_powers(self.lib, s)
            result = self.run_ability(inv, inst, ability, allow_choice)
            if isinstance(result, PendingChoice):
                result.queue = queue
                s.pending = result
                s.phase = Phase.CHOOSING
                self.emit(
                    "choice_requested",
                    seat=result.seat,
                    prompt_key=result.prompt_key,
                    option_count=len(result.options),
                )
                return True
            self.emit_power_changes(before, ability.do.value)
            queue.extend(result)
        return False

    def pending_for(
        self, inv: Invocation, prompt_key: str, options: list[str]
    ) -> list[Invocation] | PendingChoice:
        if not options:
            return []
        return PendingChoice(inv.seat, inv, prompt_key, options, [])

    def where_ok(
        self, unit: CardInstance, where: Where, acting: CardInstance, total: int | None
    ) -> bool:
        traits = self.defn(unit).traits
        if where.row_total_at_least is not None and (
            total is None or total < where.row_total_at_least
        ):
            return False
        if any(t in traits for t in where.traits_none):
            return False
        if where.traits_any and not any(t in traits for t in where.traits_any):
            return False
        return not (where.same_id_as_this and unit.card != acting.card)

    def board_candidates(
        self, seat: int, acting: CardInstance, target: Target, default_side: Side
    ) -> list[tuple[int, Row, CardInstance]]:
        s = self.s
        out: list[tuple[int, Row, CardInstance]] = []
        for bseat in self.seats_for(seat, target.side or default_side):
            for row in target.rows or ROWS:
                total = row_total(self.lib, s, bseat, row)
                for u in s.players[bseat].rows[row].units:
                    d = self.defn(u)
                    if d.kind is not Kind.UNIT or d.immune:
                        continue
                    if target.units is Units.THIS and u is not acting:
                        continue
                    if not self.where_ok(u, target.where, acting, total):
                        continue
                    out.append((bseat, row, u))
        if target.units in (Units.STRONGEST, Units.WEAKEST) and out:
            powers = [effective_power(self.lib, s, b, r, u) for b, r, u in out]
            pick = max(powers) if target.units is Units.STRONGEST else min(powers)
            out = [c for c, p in zip(out, powers, strict=True) if p == pick]
        return out

    def run_ability(
        self, inv: Invocation, inst: CardInstance, a: Ability, allow_choice: bool
    ) -> list[Invocation] | PendingChoice:
        s = self.s
        seat = inv.seat
        prompt = "choice." + a.do.value.replace("_", "-")
        if a.do is Action.DESTROY:
            cands = self.board_candidates(seat, inst, a.target or Target(), Side.OPPONENT)
            if a.choose and allow_choice:
                return self.pending_for(inv, prompt, [u.instance for _, _, u in cands])
            new: list[Invocation] = []
            for bseat, row, u in cands:
                new.extend(self.destroy_unit(bseat, row, u))
            return new
        if a.do is Action.DRAW:
            self.draw(self.side_seat(seat, a.side), a.count or 1)
            return []
        if a.do in (Action.BOOST, Action.SET_POWER):
            cands = self.board_candidates(seat, inst, a.target or Target(), Side.SELF)
            if a.choose and allow_choice:
                return self.pending_for(inv, prompt, [u.instance for _, _, u in cands])
            for _, _, u in cands:
                self.change_power(u, a)
            return []
        if a.do is Action.APPLY_ROW_EFFECT:
            if a.effect is None:
                return []
            for bseat in self.seats_for(seat, a.sides or Side.SELF):
                for row in a.rows or ROWS:
                    row_state = s.players[bseat].rows[row]
                    if a.effect not in row_state.effects:
                        row_state.effects.append(a.effect)
                        self.emit(
                            "row_effect_applied", seat=bseat, row=row.value, effect=a.effect.value
                        )
            return []
        if a.do is Action.CLEAR_ROW_EFFECTS:
            for bseat in self.seats_for(seat, a.sides or Side.BOTH):
                for row in a.rows or ROWS:
                    row_state = s.players[bseat].rows[row]
                    for effect in list(row_state.effects):
                        if a.effects is None or effect in a.effects:
                            row_state.effects.remove(effect)
                            self.emit(
                                "row_effect_cleared", seat=bseat, row=row.value, effect=effect.value
                            )
            return []
        if a.do is Action.SUMMON_FROM_DECK:
            deck = s.players[seat].deck
            matches = [
                u
                for u in deck
                if (a.same_id and u.card == inst.card) or (a.card is not None and u.card == a.card)
            ]
            if a.count is not None:
                matches = matches[: a.count]
            new = []
            for u in matches:
                deck.remove(u)
                new.extend(self.summon(seat, u, "deck"))
            return new
        if a.do is Action.RETURN_FROM_DISCARD:
            dseat = self.side_seat(seat, a.side)
            discard = s.players[dseat].discard
            units = [
                u
                for u in discard
                if self.defn(u).kind is Kind.UNIT and self.where_ok(u, a.where, inst, None)
            ]
            if a.choose and allow_choice:
                return self.pending_for(inv, prompt, [u.instance for u in units])
            new = []
            for u in units:
                discard.remove(u)
                new.extend(self.summon(seat, u, "discard"))
            return new
        if a.do is Action.SWAP_WITH_BOARD_UNIT:
            if not allow_choice:
                return []
            own = [
                u
                for bseat, _, u in self.board_units()
                if bseat == seat
                and self.defn(u).kind is Kind.UNIT
                and not self.defn(u).immune
                and self.where_ok(u, a.where, inst, None)
            ]
            return self.pending_for(inv, prompt, [u.instance for u in own])
        return []

    def apply_choice(self, inv: Invocation, a: Ability, chosen: str) -> list[Invocation]:
        s = self.s
        seat = inv.seat
        if a.do is Action.DESTROY:
            loc = self.locate(chosen)
            if loc is None:
                return []
            bseat, row, index = loc
            return self.destroy_unit(bseat, row, s.players[bseat].rows[row].units[index])
        if a.do in (Action.BOOST, Action.SET_POWER):
            loc = self.locate(chosen)
            if loc is not None:
                bseat, row, index = loc
                self.change_power(s.players[bseat].rows[row].units[index], a)
            return []
        if a.do is Action.RETURN_FROM_DISCARD:
            discard = s.players[self.side_seat(seat, a.side)].discard
            for u in discard:
                if u.instance == chosen:
                    discard.remove(u)
                    return self.summon(seat, u, "discard")
            return []
        if a.do is Action.SWAP_WITH_BOARD_UNIT:
            loc = self.locate(chosen)
            special = self.find_instance(inv.instance)
            if loc is None or special is None or special not in s.resolving:
                return []
            bseat, row, index = loc
            unit = s.players[bseat].rows[row].units[index]
            s.players[bseat].rows[row].units[index] = special
            s.resolving.remove(special)
            unit.power = self.defn(unit).power
            s.players[seat].hand.append(unit)
            self.emit("unit_returned", seat=seat, instance=unit.instance, card=unit.card, to="hand")
            self.emit(
                "card_placed",
                seat=bseat,
                instance=special.instance,
                card=special.card,
                row=row.value,
            )
            return []
        return []

    def change_power(self, unit: CardInstance, a: Ability) -> None:
        if a.do is Action.BOOST:
            unit.power += a.amount
        else:
            unit.power = a.value

    def destroy_unit(self, bseat: int, row: Row, unit: CardInstance) -> list[Invocation]:
        row_state = self.s.players[bseat].rows[row]
        row_state.units.remove(unit)
        self.s.players[bseat].discard.append(unit)
        self.emit(
            "unit_destroyed", seat=bseat, instance=unit.instance, card=unit.card, row=row.value
        )
        return [
            Invocation(unit.instance, unit.card, i, unit.owner)
            for i in self.defn(unit).triggered(Trigger.REMOVED)
        ]

    def summon(self, seat: int, unit: CardInstance, source: str) -> list[Invocation]:
        """Put a unit from the deck or the discard pile onto the board as if ``seat`` played it."""
        defn = self.defn(unit)
        unit.power = defn.power
        row = defn.rows[0]
        self.place(unit, self.side_seat(seat, defn.deploy), row)
        self.emit(
            "unit_summoned",
            seat=seat,
            instance=unit.instance,
            card=unit.card,
            row=row.value,
            side=defn.deploy.value,
            source=source,
        )
        return [
            Invocation(unit.instance, unit.card, i, seat) for i in defn.triggered(Trigger.PLAYED)
        ]

    def emit_power_changes(self, before: dict[str, tuple[int, int]], reason: str) -> None:
        for instance, (seat, power) in board_powers(self.lib, self.s).items():
            previous = before.get(instance)
            if previous is not None and previous[1] != power:
                self.emit(
                    "power_changed",
                    seat=seat,
                    instance=instance,
                    **{"from": previous[1], "to": power, "reason": reason},
                )


def acting_seat(state: MatchState) -> int | None:
    """The seat the rules are waiting on, or None when the match is over."""
    if state.phase is Phase.MULLIGAN:
        return state.mulligan_seat
    if state.phase is Phase.CHOOSING:
        return state.pending.seat if state.pending is not None else None
    if state.phase is Phase.PLAYING:
        return state.turn
    return None
