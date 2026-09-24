"""Replay scenarios — docs/protocol/cards.md rules checked as recorded matches.

A scenario file under ``tests/replays/scenarios/`` holds a seed, two small decks, the ``Rules``
and the steps of a match written with card ids, and the events and board they must lead to.
The runner turns each step into the intent it names (``play u-1 melee`` becomes the
``play_card`` of the first ``u-1`` in hand), plays the match, and then replays the resulting
record — seed, decks, rules, intents — through ``replay`` and checks it reproduces the match
exactly (``.agent/context/03-conventions.md``: replay-based tests, kept as data).

Defaults keep scenarios short: decks of any size and make-up — no unit minimum, no copy
limit — the whole deck drawn in round one, no redraws and no stratagem on the board; a
scenario may override any ``Rules`` field. Seats are
0 and 1; the seed decides who starts, and ``starter`` (default 0) states it.

File shape (YAML)::

    cards: {<id>: <card mapping>}        # added to tests.helpers.CARDS
    rules: {<Rules field>: <value>}
    seed: 3                              # an integer, expanded with seed_from_int
    starter: 0
    decks:                               # a list of card ids, or {cards, leader, stratagem}
      - [plain5, zap2]
      - {cards: [plain3], leader: leader}
    steps:                               # [seat, verb, args...]
      - [0, play, zap2, melee]           # play <card> [row] [position] — right end by default
      - [0, choose, plain3]              # choose <card> | <side>:<row>[:<position>] | <index>
      - [0, end]                         # end the turn once its card is played
      - [1, refused, error.order.not-ready, order, u-1]   # must be refused; not recorded
      - [1, pass]                        # also: order <card>|leader, cancel, end_mulligan
    events:                              # an ordered subsequence of the match's events, with
      - {type: unit_damaged, card: plain3, source: zap2}   # instance ids written as card ids
    absent: [{type: card_drawn}]         # events that must not happen
    board: {1: {melee: ["plain3:1"]}}    # card:power for units, the id alone otherwise
    graveyard: {1: [plain3]}             # also banished, and hand (compared as a multiset)
    turn: 1                              # whose turn it is at the end; phase: playing
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from opengwt.core.engine import IllegalIntent, apply, new_match
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
)
from opengwt.core.model import CardInstance, Deck, Kind, Library, MatchState, Row, Rules, Side
from opengwt.core.power import board, power_at
from opengwt.core.replay import MatchRecord, replay
from opengwt.core.rng import seed_from_int
from opengwt.core.serialize import rules_from_dict, rules_to_dict, state_hash
from opengwt.core.view import player_view
from tests.helpers import CARDS, make_library

SCENARIOS = Path(__file__).parent / "replays" / "scenarios"

BASE_RULES: dict[str, Any] = {
    "deck_min_cards": 1,
    "deck_min_units": 0,
    "copies_bronze": 99,
    "copies_gold": 99,
    "draws_per_round": [10],
    "mulligans_per_round": [0],
    "starter_extra_mulligans": 0,
    "starter_stratagem": False,
}
DEFAULT_LEADER = "leader"
DEFAULT_STRATAGEM = "strat-boost"
# event fields that hold an instance id; expectations write them as card ids
ID_FIELDS = ("instance", "source")


@dataclass
class Played:
    lib: Library
    record: MatchRecord
    state: MatchState
    events: list[Event]


def scenario_paths() -> list[Path]:
    return sorted(SCENARIOS.glob("*.yaml"))


def play_scenario(spec: dict[str, Any]) -> Played:
    lib = make_library({**CARDS, **spec.get("cards", {})})
    rules = rules_from_dict({**rules_to_dict(_default_rules()), **spec.get("rules", {})})
    decks = (_deck(spec["decks"][0]), _deck(spec["decks"][1]))
    seed = seed_from_int(int(spec["seed"]))
    state, events = new_match(lib, decks, seed, rules)
    starter = spec.get("starter", 0)
    assert state.starter == starter, f"seed {spec['seed']} gives starter {state.starter}"
    intents: list[tuple[int, Intent]] = []
    for step in spec.get("steps", []):
        seat, verb, *args = step
        if verb == "refused":  # [seat, refused, <reason key>, verb, args...]: not recorded
            reason, verb, *args = args
            intent = _intent(lib, state, int(seat), str(verb), [str(a) for a in args])
            with pytest.raises(IllegalIntent) as refusal:
                apply(lib, state, int(seat), intent)
            assert reason in (refusal.value.reason, refusal.value.code), (step, refusal.value)
            continue
        intent = _intent(lib, state, int(seat), str(verb), [str(a) for a in args])
        state, more = apply(lib, state, int(seat), intent)
        intents.append((int(seat), intent))
        events.extend(more)
    record = MatchRecord(seed, decks, tuple(intents), rules)
    again, replayed = replay(lib, record)
    assert state_hash(again) == state_hash(state), "the record does not replay to the same state"
    assert replayed == events, "the record does not replay to the same events"
    return Played(lib, record, state, events)


def check_scenario(spec: dict[str, Any], played: Played) -> None:
    names = _names(played.state)
    seen = [_readable(e, names) for e in played.events]
    wanted = list(spec.get("events", []))
    at = 0
    for event in seen:
        if at < len(wanted) and _matches(event, wanted[at]):
            at += 1
    assert at == len(wanted), (
        f"expected event not found in order: {wanted[at] if at < len(wanted) else None}\n"
        + "\n".join(str(e) for e in seen)
    )
    for forbidden in spec.get("absent", []):
        hits = [e for e in seen if _matches(e, forbidden)]
        assert not hits, f"unexpected {hits}"
    state, lib = played.state, played.lib
    for seat, rows in (spec.get("board") or {}).items():
        for row, cards in rows.items():
            assert _row(lib, state, int(seat), Row(row)) == cards, (seat, row)
    for zone in ("graveyard", "banished"):
        for seat, cards in (spec.get(zone) or {}).items():
            assert [c.card for c in getattr(state.players[int(seat)], zone)] == cards, (zone, seat)
    for seat, cards in (spec.get("hand") or {}).items():
        assert sorted(c.card for c in state.players[int(seat)].hand) == sorted(cards), seat
    if "turn" in spec:
        assert state.turn == spec["turn"]
    if "phase" in spec:
        assert state.phase.value == spec["phase"]


# --- steps --------------------------------------------------------------------------------------


def _intent(lib: Library, state: MatchState, seat: int, verb: str, args: list[str]) -> Intent:
    if verb == "play":
        inst = _in_hand(state, seat, args[0])
        defn = lib[inst.card]
        if not defn.placed:
            return PlayCard(inst.instance)
        row = Row(args[1]) if len(args) > 1 else Row.MELEE
        land = 1 - seat if defn.kind is Kind.UNIT and defn.side is Side.OPPONENT else seat
        position = int(args[2]) if len(args) > 2 else len(state.players[land].rows[row].cards)
        return PlayCard(inst.instance, row, position)
    if verb == "choose":
        return Choose(_option(lib, state, seat, args[0]))
    if verb == "order":
        return UseOrder(_order_card(state, seat, args[0]))
    if verb == "cancel":
        return CancelChoice()
    if verb == "pass":
        return Pass()
    if verb == "end":
        return EndTurn()
    if verb == "end_mulligan":
        return EndMulligan()
    raise ValueError(f"unknown step verb {verb!r}")


def _in_hand(state: MatchState, seat: int, card: str) -> CardInstance:
    for inst in state.players[seat].hand:
        if inst.card == card:
            return inst
    raise AssertionError(f"no {card} in seat {seat}'s hand")


def _order_card(state: MatchState, seat: int, card: str) -> str:
    leader = state.players[seat].leader
    if card == "leader" and leader is not None:
        return leader.instance
    for loc in board(state, seat):
        if loc.seat == seat and loc.card.card == card:
            return loc.card.instance
    raise AssertionError(f"no {card} on seat {seat}'s side")


def _option(lib: Library, state: MatchState, seat: int, wanted: str) -> int:
    pending = player_view(lib, state, seat)["pending_choice"]
    assert pending is not None, f"no choice pending for seat {seat}"
    if wanted.isdigit():
        return int(wanted)
    for i, option in enumerate(pending["options"]):
        if ":" in wanted:
            parts = wanted.split(":")
            keys = ("side", "row", "position")[: len(parts)]
            if all(str(option.get(k)) == v for k, v in zip(keys, parts, strict=True)):
                return i
        elif option.get("card") == wanted:
            return i
    raise AssertionError(f"no option {wanted!r} in {pending['options']}")


# --- expectations -------------------------------------------------------------------------------


def _default_rules() -> Rules:
    return rules_from_dict({**rules_to_dict(Rules()), **BASE_RULES})


def _deck(spec: Any) -> Deck:
    if isinstance(spec, list):
        spec = {"cards": spec}
    return Deck(
        "test",
        tuple(str(c) for c in spec["cards"]),
        str(spec.get("leader", DEFAULT_LEADER)),
        str(spec.get("stratagem", DEFAULT_STRATAGEM)),
    )


def _names(state: MatchState) -> dict[str, str]:
    cards: list[CardInstance] = list(state.resolving)
    for p in state.players:
        cards += p.deck + p.hand + p.graveyard + p.banished
        cards += [c for side in p.rows.values() for c in side.cards]
        if p.leader is not None:
            cards.append(p.leader)
    return {c.instance: c.card for c in cards}


def _readable(event: Event, names: dict[str, str]) -> dict[str, Any]:
    d = event_to_dict(event)
    d.pop("seq")
    for key in ID_FIELDS:
        if isinstance(d.get(key), str):
            d[key] = names.get(d[key], d[key])
    return d


def _matches(event: dict[str, Any], wanted: dict[str, Any]) -> bool:
    for key, value in wanted.items():
        actual = event.get("instance") if key == "card" and "card" not in event else event.get(key)
        if actual != value:
            return False
    return True


def _row(lib: Library, state: MatchState, seat: int, row: Row) -> list[str]:
    out: list[str] = []
    for i, c in enumerate(state.players[seat].rows[row].cards):
        if lib[c.card].kind is Kind.UNIT:
            out.append(f"{c.card}:{power_at(lib, state, seat, row, i)}")
        else:
            out.append(c.card)
    return out


def load_scenario(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), path
    return data
