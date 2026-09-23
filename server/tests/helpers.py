"""Test scaffolding: a small card vocabulary and a way to set up a board directly."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from opengwt.core.engine import apply
from opengwt.core.events import Event
from opengwt.core.intents import Choose, EndTurn, PlayCard
from opengwt.core.model import (
    CardInstance,
    Kind,
    Library,
    MatchState,
    Phase,
    PlayerState,
    Row,
    RowSide,
    Rules,
    Side,
    Status,
    StatusEntry,
    card_def_from_mapping,
)
from opengwt.core.power import board, power_at
from opengwt.core.rng import seed_from_int

MELEE, RANGED = Row.MELEE, Row.RANGED


def _unit(power: int, **extra: Any) -> dict[str, Any]:
    return {"kind": "unit", "color": "bronze", "provisions": 4, "power": power, **extra}


def _special(*abilities: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "special", "color": "bronze", "provisions": 4, "abilities": list(abilities)}


def _on_play(do: str, **params: Any) -> dict[str, Any]:
    return {"when": "on_play", "do": do, **params}


def _if(condition: dict[str, Any], ability: dict[str, Any]) -> dict[str, Any]:
    return {**ability, "if": condition}


THIS = {"units": "this"}
CHOSEN_ENEMY = {"units": "chosen", "side": "opponent"}
CHOSEN_ALLY = {"units": "chosen", "side": "self"}
MELEE_ENEMY_ROW = {"pick": "all", "side": "opponent", "rows": ["melee"]}

CARDS: dict[str, dict[str, Any]] = {
    "plain5": _unit(5),
    "plain3": _unit(3),
    "plain8": _unit(8),
    "spare": _unit(1),  # scenarios keep one in hand, so that nobody passes automatically
    "melee4": _unit(4, rows=["melee"]),
    "armored4": _unit(4, armor=3),
    "shield4": _unit(4, statuses=["shielded"]),
    "immune6": _unit(6, statuses=["immune"]),
    "guard6": _unit(6, statuses=["guarding"]),
    "proof4": _unit(4, statuses=["status_proof"]),
    "kept3": _unit(3, statuses=["kept_at_round_end"]),
    "doomed5": _unit(5, statuses=["banish_on_leave"]),
    "aura-row": _unit(
        2,
        abilities=[
            {"when": "while_on_board", "do": "continuous_boost", "amount": 1, "scope": "row"}
        ],
    ),
    "aura-adj": _unit(
        2,
        abilities=[
            {"when": "while_on_board", "do": "continuous_boost", "amount": 2, "scope": "adjacent"}
        ],
    ),
    "spy7": _unit(7, side="opponent", abilities=[_on_play("draw", count=1)]),
    "zap2": _unit(3, abilities=[_on_play("damage", amount=2, target=CHOSEN_ENEMY)]),
    "grow3": _unit(3, abilities=[_on_play("add_status", status="growing", turns=3, target=THIS)]),
    "drain3": _unit(2, abilities=[_on_play("drain", amount=3, target=CHOSEN_ENEMY)]),
    "duel": _unit(5, abilities=[_on_play("duel", target=CHOSEN_ENEMY)]),
    "consume": _unit(1, abilities=[_on_play("consume", target=CHOSEN_ALLY)]),
    "muster": _unit(
        3,
        abilities=[
            _on_play("summon_from_deck", cards={"pick": "all", "where": {"same_id_as_this": True}})
        ],
    ),
    "token-maker": _unit(2, abilities=[_on_play("place_new_card", card="tok", count=2)]),
    "tok": {"kind": "unit", "token": True, "power": 1, "tags": ["tb"]},
    "round-end-boost": _unit(
        3, abilities=[{"when": "on_round_end", "do": "boost", "amount": 2, "target": THIS}]
    ),
    "adrenaline": _unit(
        2, abilities=[_if({"hand_at_most": 1}, _on_play("boost", amount=5, target=THIS))]
    ),
    "devotion": _unit(
        2,
        abilities=[
            _if({"starting_deck_without_neutral": True}, _on_play("boost", amount=3, target=THIS))
        ],
    ),
    "bloodthirst": _unit(
        2,
        abilities=[
            _if(
                {"units_at_least": {"count": 1, "side": "opponent", "where": {"damaged": True}}},
                _on_play("boost", amount=4, target=THIS),
            )
        ],
    ),
    "deathwish": _unit(3, abilities=[{"when": "on_destroyed", "do": "draw", "count": 1}]),
    "zap-all": _special(_on_play("damage", amount=1, target={"units": "all", "side": "opponent"})),
    "rain2": _special(
        _on_play("damage", amount=1, target={"units": "random", "side": "opponent", "count": 2})
    ),
    "poison": _special(_on_play("add_status", status="poisoned", target=CHOSEN_ENEMY)),
    "lock": _special(
        _on_play(
            "add_status",
            status="locked",
            target={"units": "chosen", "side": "both", "where": {"kind": ["unit", "artifact"]}},
        )
    ),
    "bleed2": _special(_on_play("add_status", status="bleeding", turns=2, target=CHOSEN_ENEMY)),
    "grow-ally2": _special(_on_play("add_status", status="growing", turns=2, target=CHOSEN_ALLY)),
    "shield-ally": _special(_on_play("add_status", status="shielded", target=CHOSEN_ALLY)),
    "heal-all": _special(_on_play("heal", target={"units": "all", "side": "self"})),
    "reset": _special(_on_play("reset_power", target={"units": "chosen", "side": "both"})),
    "raise2": _special(_on_play("raise_base_power", amount=2, target=CHOSEN_ALLY)),
    "armor2": _special(_on_play("add_armor", amount=2, target=CHOSEN_ALLY)),
    "boost3": _special(_on_play("boost", amount=3, target=CHOSEN_ALLY)),
    "scorch": _special(_on_play("destroy", target={"units": "strongest", "side": "both"})),
    "seize": _special(_on_play("take_control", target=CHOSEN_ENEMY)),
    "recall": _special(_on_play("return_to_hand", target=CHOSEN_ALLY)),
    "shove": _special(_on_play("move_to_other_row", target=CHOSEN_ENEMY)),
    "exile": _special(_on_play("banish", target={"units": "chosen", "side": "both"})),
    "purify": _special(_on_play("remove_statuses", target={"units": "all", "side": "self"})),
    "discard2": _special(_on_play("discard", cards={"pick": "random", "count": 2})),
    "draw2": _special(_on_play("draw", count=2)),
    "frost": _special(
        _on_play("set_row_effect", effect="damage_weakest", amount=2, row_target=MELEE_ENEMY_ROW)
    ),
    "fog": _special(
        _on_play("set_row_effect", effect="damage_strongest", amount=2, row_target=MELEE_ENEMY_ROW)
    ),
    "froth": _special(
        _on_play(
            "set_row_effect",
            effect="boost_random",
            amount=1,
            count=2,
            row_target={"pick": "all", "side": "self", "rows": ["melee"]},
        )
    ),
    "trap": _special(
        _on_play("set_row_effect", effect="damage_on_arrival", amount=2, row_target=MELEE_ENEMY_ROW)
    ),
    "clear-hazards": _special(
        _on_play("clear_row_effect", only="hazard", row_target={"pick": "all", "side": "both"})
    ),
    "relic": {
        "kind": "artifact",
        "color": "bronze",
        "provisions": 5,
        "abilities": [
            {"when": "while_on_board", "do": "continuous_boost", "amount": 1, "scope": "row"}
        ],
    },
    "strat-boost": {
        "kind": "stratagem",
        "abilities": [{"when": "on_activate", "do": "boost", "amount": 3, "target": CHOSEN_ALLY}],
    },
    "strat-draw": {
        "kind": "stratagem",
        "rows": ["ranged"],
        "abilities": [
            {"when": "on_activate", "do": "draw", "count": 1},
            {"when": "on_activate", "do": "boost", "amount": 1, "target": CHOSEN_ALLY},
        ],
    },
    "leader": {
        "kind": "leader",
        "provision_bonus": 15,
        "activation": {"charges": 1},
        "abilities": [{"when": "on_activate", "do": "boost", "amount": 2, "target": CHOSEN_ALLY}],
    },
}

FILLER: tuple[str, ...] = ("plain5", "plain5")

BoardSpec = dict[str, Iterable[str | tuple[str, int]]]


def make_library(cards: dict[str, dict[str, Any]] | None = None, faction: str = "test") -> Library:
    return {cid: card_def_from_mapping(cid, faction, m) for cid, m in (cards or CARDS).items()}


class Builder:
    """Builds a match state in the playing phase with exactly the cards you name. Board cards
    are set up as the engine places them: base and current power from the definition, printed
    armour, innate statuses, and ``on_enemy_side`` for a card owned by the other seat — given as
    ``(card, owner)``."""

    def __init__(self, lib: Library) -> None:
        self.lib = lib
        self.next = 1

    def inst(self, card: str, owner: int) -> CardInstance:
        d = self.lib[card]
        inst = CardInstance(
            f"c{self.next}",
            card,
            owner,
            base=d.power,
            power=d.power,
            charges=d.activation.charges if d.activation else None,
        )
        self.next += 1
        return inst

    def on_board(self, spec: str | tuple[str, int], seat: int) -> CardInstance:
        card, owner = (spec, seat) if isinstance(spec, str) else spec
        inst = self.inst(card, owner)
        d = self.lib[card]
        inst.armor = d.armor
        inst.statuses = [StatusEntry(s) for s in d.statuses]
        if owner != seat:
            inst.statuses.append(StatusEntry(Status.ON_ENEMY_SIDE))
        return inst

    def state(
        self,
        hand0: Iterable[str] | None = None,
        hand1: Iterable[str] | None = None,
        deck0: Iterable[str] = (),
        deck1: Iterable[str] = (),
        grave0: Iterable[str] = (),
        grave1: Iterable[str] = (),
        board0: BoardSpec | None = None,
        board1: BoardSpec | None = None,
        leaders: tuple[str | None, str | None] = (None, None),
        turn: int = 0,
        rules: Rules | None = None,
    ) -> MatchState:
        # A player with an empty hand is passed automatically, which would end the round in
        # the middle of a test; give both seats a couple of plain cards unless told otherwise.
        rules = rules or Rules()
        hand0 = FILLER if hand0 is None else hand0
        hand1 = FILLER if hand1 is None else hand1
        players: list[PlayerState] = []
        for seat, (hand, deck, grave, spec, leader) in enumerate(
            (
                (hand0, deck0, grave0, board0, leaders[0]),
                (hand1, deck1, grave1, board1, leaders[1]),
            )
        ):
            rows = {row: RowSide() for row in rules.rows}
            for row_name, cards in (spec or {}).items():
                rows[Row(row_name)].cards = [self.on_board(c, seat) for c in cards]
            players.append(
                PlayerState(
                    seat=seat,
                    faction="test",
                    deck=[self.inst(c, seat) for c in deck],
                    hand=[self.inst(c, seat) for c in hand],
                    graveyard=[self.inst(c, seat) for c in grave],
                    banished=[],
                    rows=rows,
                    leader=self.inst(leader, seat) if leader else None,
                )
            )
        return MatchState(
            rules=rules,
            seed=seed_from_int(1),
            rng_block=0,
            rng_pos=0,
            next_instance=0,
            phase=Phase.PLAYING,
            round=1,
            starter=turn,
            turn=turn,
            active=turn,
            players=players,
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
    lib: Library,
    state: MatchState,
    seat: int,
    card: str,
    row: Row | None = None,
    position: int | None = None,
    end: bool = True,
) -> tuple[MatchState, list[Event]]:
    """Play a card from hand; a unit or artifact goes to the right end of ``row`` (melee by
    default) unless ``position`` says otherwise. With ``end``, the turn is then ended, unless a
    choice is pending (``choose`` ends it once the choice is made)."""
    defn = lib[card]
    if defn.placed:
        row = row or MELEE
        if position is None:
            opposite = defn.kind is Kind.UNIT and defn.side is Side.OPPONENT
            land = 1 - seat if opposite else seat
            position = len(state.players[land].rows[row].cards)
    state, events = apply(
        lib, state, seat, PlayCard(hand_instance(state, seat, card), row, position)
    )
    return end_turn(lib, state, seat, events) if end else (state, events)


def choose(
    lib: Library, state: MatchState, seat: int, option: int = 0, end: bool = True
) -> tuple[MatchState, list[Event]]:
    """Make a pending choice; with ``end``, end the turn once the played card has resolved."""
    state, events = apply(lib, state, seat, Choose(option))
    return end_turn(lib, state, seat, events) if end else (state, events)


def end_turn(
    lib: Library, state: MatchState, seat: int, events: list[Event]
) -> tuple[MatchState, list[Event]]:
    """End ``seat``'s turn if its card has been played and nothing is pending."""
    if state.phase is Phase.PLAYING and state.turn == seat and state.played:
        state, more = apply(lib, state, seat, EndTurn())
        events = [*events, *more]
    return state, events


def cards_on(state: MatchState, seat: int, row: Row) -> list[str]:
    return [u.card for u in state.players[seat].rows[row].cards]


def powers_on(lib: Library, state: MatchState, seat: int, row: Row) -> list[int]:
    cards = state.players[seat].rows[row].cards
    return [power_at(lib, state, seat, row, i) for i in range(len(cards))]


def unit(state: MatchState, card: str, seat: int | None = None) -> CardInstance:
    """The first card with this id on the board, optionally on one seat's side."""
    for loc in board(state, 0):
        if loc.card.card == card and (seat is None or loc.seat == seat):
            return loc.card
    raise KeyError(card)


def statuses(card: CardInstance) -> list[tuple[str, int | None]]:
    return [(e.status.value, e.turns) for e in card.statuses]


def event_types(events: list[Event]) -> list[str]:
    return [e.type for e in events]


def events_of(events: list[Event], type_: str) -> list[dict[str, Any]]:
    return [e.data for e in events if e.type == type_]
