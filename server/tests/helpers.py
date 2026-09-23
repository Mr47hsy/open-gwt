"""Test scaffolding: a tiny card vocabulary and a way to set up a board directly."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from opengwt.core.engine import apply
from opengwt.core.events import Event
from opengwt.core.intents import PlayCard
from opengwt.core.model import (
    ROWS,
    CardInstance,
    Library,
    MatchState,
    Phase,
    PlayerState,
    Row,
    RowState,
    Rules,
    card_def_from_mapping,
)
from opengwt.core.rng import Pcg32

CARDS: dict[str, dict[str, Any]] = {
    "plain5": {"kind": "unit", "rows": ["melee"], "power": 5},
    "plain8r": {"kind": "unit", "rows": ["ranged"], "power": 8},
    "flex6": {"kind": "unit", "rows": ["ranged", "siege"], "power": 6},
    "immune10": {"kind": "unit", "rows": ["melee"], "power": 10, "traits": ["immune"]},
    "bond4": {
        "kind": "unit",
        "rows": ["melee"],
        "power": 4,
        "abilities": [{"when": "always", "do": "multiply_power_by_copies"}],
    },
    "morale1": {
        "kind": "unit",
        "rows": ["melee"],
        "power": 1,
        "abilities": [{"when": "always", "do": "boost_row_others", "amount": 1}],
    },
    "spy4": {
        "kind": "unit",
        "rows": ["melee"],
        "power": 4,
        "deploy": "opponent",
        "abilities": [{"when": "played", "do": "draw", "count": 2}],
    },
    "medic": {
        "kind": "unit",
        "rows": ["ranged"],
        "power": 5,
        "abilities": [
            {
                "when": "played",
                "do": "return_from_discard",
                "where": {"traits_none": ["immune"]},
                "choose": "player",
            }
        ],
    },
    "muster": {
        "kind": "unit",
        "rows": ["siege"],
        "power": 3,
        "abilities": [{"when": "played", "do": "summon_from_deck", "same_id": True}],
    },
    "boost-siege": {
        "kind": "unit",
        "rows": ["siege"],
        "power": 2,
        "abilities": [
            {
                "when": "played",
                "do": "boost",
                "target": {"side": "self", "rows": ["siege"]},
                "amount": 2,
            }
        ],
    },
    "frost": {
        "kind": "special",
        "abilities": [
            {
                "when": "played",
                "do": "apply_row_effect",
                "effect": "power_to_one",
                "rows": ["melee"],
                "sides": "both",
            }
        ],
    },
    "clear": {"kind": "special", "abilities": [{"when": "played", "do": "clear_row_effects"}]},
    "horn-melee": {
        "kind": "special",
        "abilities": [
            {
                "when": "played",
                "do": "apply_row_effect",
                "effect": "double_power",
                "rows": ["melee"],
                "sides": "self",
            }
        ],
    },
    "decoy": {
        "kind": "special",
        "abilities": [
            {
                "when": "played",
                "do": "swap_with_board_unit",
                "where": {"traits_none": ["immune"]},
                "choose": "player",
            }
        ],
    },
    "scorch": {
        "kind": "special",
        "abilities": [
            {"when": "played", "do": "destroy", "target": {"side": "both", "units": "strongest"}}
        ],
    },
    "row-scorch": {
        "kind": "special",
        "abilities": [
            {
                "when": "played",
                "do": "destroy",
                "target": {
                    "side": "opponent",
                    "rows": ["melee"],
                    "units": "strongest",
                    "where": {"row_total_at_least": 10},
                },
            }
        ],
    },
    "draw2": {"kind": "special", "abilities": [{"when": "played", "do": "draw", "count": 2}]},
    "leader-clear": {
        "kind": "leader",
        "abilities": [{"when": "activated", "do": "clear_row_effects"}],
    },
}


FILLER: tuple[str, ...] = ("plain5", "plain5")


def make_library(cards: dict[str, dict[str, Any]] | None = None, faction: str = "test") -> Library:
    return {cid: card_def_from_mapping(cid, faction, m) for cid, m in (cards or CARDS).items()}


class Builder:
    """Builds a match state in the playing phase with exactly the cards you name."""

    def __init__(self, lib: Library) -> None:
        self.lib = lib
        self.next = 1

    def inst(self, card: str, owner: int) -> CardInstance:
        inst = CardInstance(f"c{self.next}", card, owner, self.lib[card].power)
        self.next += 1
        return inst

    def state(
        self,
        hand0: Iterable[str] | None = None,
        hand1: Iterable[str] | None = None,
        deck0: Iterable[str] = (),
        deck1: Iterable[str] = (),
        discard0: Iterable[str] = (),
        discard1: Iterable[str] = (),
        board0: dict[str, Iterable[str]] | None = None,
        board1: dict[str, Iterable[str]] | None = None,
        leaders: tuple[str | None, str | None] = (None, None),
        turn: int = 0,
    ) -> MatchState:
        # A player with an empty hand is passed automatically, which would end the round in
        # the middle of a test; give both seats a couple of plain cards unless told otherwise.
        if hand0 is None:
            hand0 = FILLER
        if hand1 is None:
            hand1 = FILLER
        rng = Pcg32(1)
        players: list[PlayerState] = []
        for seat, (hand, deck, discard, board, leader) in enumerate(
            (
                (hand0, deck0, discard0, board0, leaders[0]),
                (hand1, deck1, discard1, board1, leaders[1]),
            )
        ):
            rows = {row: RowState() for row in ROWS}
            for row_name, cards in (board or {}).items():
                rows[Row(row_name)].units = [self.inst(c, seat) for c in cards]
            players.append(
                PlayerState(
                    seat=seat,
                    faction="test",
                    deck=[self.inst(c, seat) for c in deck],
                    hand=[self.inst(c, seat) for c in hand],
                    discard=[self.inst(c, seat) for c in discard],
                    rows=rows,
                    leader=self.inst(leader, seat) if leader else None,
                    mulligan_done=True,
                )
            )
        return MatchState(
            rules=Rules(min_units=0),
            seed=1,
            rng_state=rng.state,
            rng_inc=rng.inc,
            phase=Phase.PLAYING,
            round=1,
            starter=turn,
            turn=turn,
            mulligan_seat=None,
            players=players,
            next_instance=self.next,
            seq=0,
            winner=None,
            pending=None,
            resolving=[],
            rounds=[],
        )


def hand_instance(state: MatchState, seat: int, card: str) -> str:
    for inst in state.players[seat].hand:
        if inst.card == card:
            return inst.instance
    raise KeyError(card)


def play(
    lib: Library, state: MatchState, seat: int, card: str, row: Row | None = None
) -> tuple[MatchState, list[Event]]:
    return apply(lib, state, seat, PlayCard(hand_instance(state, seat, card), row))


def cards_on(state: MatchState, seat: int, row: Row) -> list[str]:
    return [u.card for u in state.players[seat].rows[row].units]


def event_types(events: list[Event]) -> list[str]:
    return [e.type for e in events]
