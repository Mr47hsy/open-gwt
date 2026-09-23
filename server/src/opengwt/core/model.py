"""Vocabulary and state of the rules core.

Definitions (``CardDef`` and friends) are immutable and built from plain mappings that follow
``docs/protocol/cards.md``. Match state is mutable and only ever changed by ``engine.apply``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Kind(str, Enum):
    UNIT = "unit"
    SPECIAL = "special"
    LEADER = "leader"


class Row(str, Enum):
    MELEE = "melee"
    RANGED = "ranged"
    SIEGE = "siege"


ROWS: tuple[Row, ...] = (Row.MELEE, Row.RANGED, Row.SIEGE)


class Side(str, Enum):
    SELF = "self"
    OPPONENT = "opponent"
    BOTH = "both"


class Trait(str, Enum):
    IMMUNE = "immune"


class RowEffect(str, Enum):
    POWER_TO_ONE = "power_to_one"
    DOUBLE_POWER = "double_power"


class Trigger(str, Enum):
    PLAYED = "played"
    ACTIVATED = "activated"
    ALWAYS = "always"
    ROUND_END = "round_end"
    TURN_START = "turn_start"
    REMOVED = "removed"


class Action(str, Enum):
    DESTROY = "destroy"
    DRAW = "draw"
    BOOST = "boost"
    SET_POWER = "set_power"
    APPLY_ROW_EFFECT = "apply_row_effect"
    CLEAR_ROW_EFFECTS = "clear_row_effects"
    SUMMON_FROM_DECK = "summon_from_deck"
    RETURN_FROM_DISCARD = "return_from_discard"
    SWAP_WITH_BOARD_UNIT = "swap_with_board_unit"
    MULTIPLY_POWER_BY_COPIES = "multiply_power_by_copies"
    BOOST_ROW_OTHERS = "boost_row_others"


PASSIVE_ACTIONS = frozenset({Action.MULTIPLY_POWER_BY_COPIES, Action.BOOST_ROW_OTHERS})


class Units(str, Enum):
    ALL = "all"
    STRONGEST = "strongest"
    WEAKEST = "weakest"
    THIS = "this"


class Phase(str, Enum):
    MULLIGAN = "mulligan"
    PLAYING = "playing"
    CHOOSING = "choosing"
    MATCH_OVER = "match_over"


# --- definitions -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Where:
    row_total_at_least: int | None = None
    traits_none: tuple[Trait, ...] = ()
    traits_any: tuple[Trait, ...] = ()
    same_id_as_this: bool = False


@dataclass(frozen=True)
class Target:
    side: Side | None = None
    rows: tuple[Row, ...] | None = None
    units: Units = Units.ALL
    where: Where = Where()


@dataclass(frozen=True)
class Ability:
    when: Trigger
    do: Action
    target: Target | None = None
    choose: bool = False
    side: Side = Side.SELF
    count: int | None = None
    amount: int = 0
    value: int = 0
    effect: RowEffect | None = None
    rows: tuple[Row, ...] | None = None
    sides: Side | None = None
    same_id: bool = False
    card: str | None = None
    where: Where = Where()
    effects: tuple[RowEffect, ...] | None = None


@dataclass(frozen=True)
class CardDef:
    id: str
    kind: Kind
    faction: str
    rows: tuple[Row, ...] = ()
    power: int = 0
    deploy: Side = Side.SELF
    traits: tuple[Trait, ...] = ()
    abilities: tuple[Ability, ...] = ()

    @property
    def immune(self) -> bool:
        return Trait.IMMUNE in self.traits

    def passives(self, action: Action) -> tuple[Ability, ...]:
        return tuple(a for a in self.abilities if a.when is Trigger.ALWAYS and a.do is action)

    def triggered(self, when: Trigger) -> tuple[int, ...]:
        """Indices of abilities with the given trigger, in card order."""
        return tuple(i for i, a in enumerate(self.abilities) if a.when is when)


Library = dict[str, CardDef]


@dataclass(frozen=True)
class Deck:
    faction: str
    cards: tuple[str, ...]
    leader: str | None = None


@dataclass(frozen=True)
class Rules:
    hand_size: int = 10
    mulligan_max: int = 2
    lives: int = 2
    min_units: int = 22
    max_specials: int = 10


DEFAULT_RULES = Rules()


def _where(m: Mapping[str, Any]) -> Where:
    return Where(
        row_total_at_least=m.get("row_total_at_least"),
        traits_none=tuple(Trait(t) for t in m.get("traits_none", ())),
        traits_any=tuple(Trait(t) for t in m.get("traits_any", ())),
        same_id_as_this=bool(m.get("same_id_as_this", False)),
    )


def _target(m: Mapping[str, Any]) -> Target:
    return Target(
        side=Side(m["side"]) if "side" in m else None,
        rows=tuple(Row(r) for r in m["rows"]) if "rows" in m else None,
        units=Units(m.get("units", "all")),
        where=_where(m.get("where", {})),
    )


def _ability(m: Mapping[str, Any]) -> Ability:
    return Ability(
        when=Trigger(m["when"]),
        do=Action(m["do"]),
        target=_target(m["target"]) if "target" in m else None,
        choose=m.get("choose") == "player",
        side=Side(m.get("side", "self")),
        count=m.get("count"),
        amount=int(m.get("amount", 0)),
        value=int(m.get("value", 0)),
        effect=RowEffect(m["effect"]) if "effect" in m else None,
        rows=tuple(Row(r) for r in m["rows"]) if "rows" in m else None,
        sides=Side(m["sides"]) if "sides" in m else None,
        same_id=bool(m.get("same_id", False)),
        card=m.get("card"),
        where=_where(m.get("where", {})),
        effects=tuple(RowEffect(e) for e in m["effects"]) if "effects" in m else None,
    )


def card_def_from_mapping(card_id: str, faction: str, m: Mapping[str, Any]) -> CardDef:
    """Build a definition from a mapping shaped like one entry of a cards file."""
    return CardDef(
        id=card_id,
        kind=Kind(m["kind"]),
        faction=faction,
        rows=tuple(Row(r) for r in m.get("rows", ())),
        power=int(m.get("power", 0)),
        deploy=Side(m.get("deploy", "self")),
        traits=tuple(Trait(t) for t in m.get("traits", ())),
        abilities=tuple(_ability(a) for a in m.get("abilities", ())),
    )


# --- match state -------------------------------------------------------------------------------


@dataclass
class CardInstance:
    instance: str
    card: str
    owner: int
    power: int


@dataclass
class RowState:
    """``effects`` is a set kept as an ordered list: at most one entry per effect kind."""

    effects: list[RowEffect] = field(default_factory=list)
    units: list[CardInstance] = field(default_factory=list)


@dataclass
class PlayerState:
    seat: int
    faction: str
    deck: list[CardInstance]
    hand: list[CardInstance]
    discard: list[CardInstance]
    rows: dict[Row, RowState]
    leader: CardInstance | None
    leader_used: bool = False
    passed: bool = False
    lives: int = 2
    rounds_won: int = 0
    mulligan_done: bool = False


@dataclass
class Invocation:
    """One ability of one card instance, waiting to be resolved on behalf of ``seat``."""

    instance: str
    card: str
    ability_index: int
    seat: int


@dataclass
class PendingChoice:
    seat: int
    invocation: Invocation
    prompt_key: str
    options: list[str]
    queue: list[Invocation]


@dataclass
class RoundResult:
    round: int
    winner: int | None
    scores: tuple[int, int]


@dataclass
class MatchState:
    rules: Rules
    seed: int
    rng_state: int
    rng_inc: int
    phase: Phase
    round: int
    starter: int
    turn: int | None
    mulligan_seat: int | None
    players: list[PlayerState]
    next_instance: int
    seq: int
    winner: int | None
    pending: PendingChoice | None
    resolving: list[CardInstance]
    rounds: list[RoundResult]

    def other(self, seat: int) -> int:
        return 1 - seat
