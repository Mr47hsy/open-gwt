"""Vocabulary and state of the rules core — docs/protocol/cards.md (``opengwt.cards/2``).

Definitions (``CardDef`` and friends) are immutable and built from plain mappings shaped like the
cards files. The whole v2 vocabulary loads and acts: ADR 0009 phase B implemented the power and
board words, phase C the triggers, activation and generalised choices (``phase_c_words`` lists
the words of a card that phase C gave behaviour to). Match state is mutable and only ever changed
by ``engine.apply``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Kind(str, Enum):
    UNIT = "unit"
    SPECIAL = "special"
    ARTIFACT = "artifact"
    LEADER = "leader"
    STRATAGEM = "stratagem"


class Color(str, Enum):
    BRONZE = "bronze"
    GOLD = "gold"


class Row(str, Enum):
    MELEE = "melee"
    RANGED = "ranged"


class Side(str, Enum):
    SELF = "self"
    OPPONENT = "opponent"
    BOTH = "both"


class Status(str, Enum):
    LOCKED = "locked"
    SHIELDED = "shielded"
    IMMUNE = "immune"
    POISONED = "poisoned"
    BLEEDING = "bleeding"
    GROWING = "growing"
    BANISH_ON_LEAVE = "banish_on_leave"
    KEPT_AT_ROUND_END = "kept_at_round_end"
    STATUS_PROOF = "status_proof"
    GUARDING = "guarding"
    ON_ENEMY_SIDE = "on_enemy_side"


# Statuses that take a timer: required for the first two, optional for the rest (cards.md §9).
TIMER_REQUIRED = frozenset({Status.BLEEDING, Status.GROWING})
TIMER_OPTIONAL = frozenset({Status.LOCKED, Status.IMMUNE, Status.STATUS_PROOF, Status.GUARDING})
# What an artifact can carry; any other status added to one does nothing.
ARTIFACT_STATUSES = frozenset(
    {
        Status.LOCKED,
        Status.IMMUNE,
        Status.BANISH_ON_LEAVE,
        Status.KEPT_AT_ROUND_END,
        Status.STATUS_PROOF,
        Status.ON_ENEMY_SIDE,
    }
)
# Kept by the board itself: never added or removed by an action.
AUTOMATIC_STATUSES = frozenset({Status.ON_ENEMY_SIDE})


class RowEffectKind(str, Enum):
    DAMAGE_STRONGEST = "damage_strongest"
    DAMAGE_WEAKEST = "damage_weakest"
    DAMAGE_RANDOM = "damage_random"
    BOOST_RANDOM = "boost_random"
    DAMAGE_ON_ARRIVAL = "damage_on_arrival"


class RowEffectClass(str, Enum):
    HAZARD = "hazard"
    BOON = "boon"


BOONS = frozenset({RowEffectKind.BOOST_RANDOM})


def row_effect_class(effect: RowEffectKind) -> RowEffectClass:
    return RowEffectClass.BOON if effect in BOONS else RowEffectClass.HAZARD


class Trigger(str, Enum):
    ON_PLAY = "on_play"
    ON_ACTIVATE = "on_activate"
    ON_DESTROYED = "on_destroyed"
    ON_TURN_START = "on_turn_start"
    ON_TURN_END = "on_turn_end"
    ON_ROUND_END = "on_round_end"
    ON_ALLY_PLAYED = "on_ally_played"
    ON_BOOSTED = "on_boosted"
    ON_DAMAGED = "on_damaged"
    WHILE_ON_BOARD = "while_on_board"


class Action(str, Enum):
    DAMAGE = "damage"
    BOOST = "boost"
    ADD_ARMOR = "add_armor"
    HEAL = "heal"
    RESET_POWER = "reset_power"
    RAISE_BASE_POWER = "raise_base_power"
    DESTROY = "destroy"
    BANISH = "banish"
    ADD_STATUS = "add_status"
    REMOVE_STATUSES = "remove_statuses"
    MOVE_TO_OTHER_ROW = "move_to_other_row"
    RETURN_TO_HAND = "return_to_hand"
    TAKE_CONTROL = "take_control"
    DRAIN = "drain"
    DUEL = "duel"
    CONSUME = "consume"
    DISCARD = "discard"
    DRAW = "draw"
    PLAY_FROM_DECK = "play_from_deck"
    PLAY_FROM_GRAVEYARD = "play_from_graveyard"
    SUMMON_FROM_DECK = "summon_from_deck"
    PLACE_NEW_CARD = "place_new_card"
    CREATE = "create"
    ADD_CHARGES = "add_charges"
    SET_ROW_EFFECT = "set_row_effect"
    CLEAR_ROW_EFFECT = "clear_row_effect"
    CONTINUOUS_BOOST = "continuous_boost"


# Actions on a unit's power; they never affect an artifact (cards.md §7.1).
POWER_ACTIONS = frozenset(
    {
        Action.DAMAGE,
        Action.BOOST,
        Action.ADD_ARMOR,
        Action.HEAL,
        Action.RESET_POWER,
        Action.RAISE_BASE_POWER,
        Action.DRAIN,
        Action.DUEL,
        Action.CONSUME,
    }
)


class Units(str, Enum):
    CHOSEN = "chosen"
    CHOSEN_ROW = "chosen_row"
    ALL = "all"
    RANDOM = "random"
    STRONGEST = "strongest"
    WEAKEST = "weakest"
    THIS = "this"
    ADJACENT = "adjacent"
    TRIGGER_UNIT = "trigger_unit"
    PREVIOUS_TARGETS = "previous_targets"


class RowPick(str, Enum):
    CHOSEN = "chosen"
    ALL = "all"
    THIS = "this"


class CardPick(str, Enum):
    CHOSEN = "chosen"
    RANDOM = "random"
    FIRST = "first"
    ALL = "all"


class Scope(str, Enum):
    ROW = "row"
    ADJACENT = "adjacent"


class ChargeTarget(str, Enum):
    THIS = "this"
    LEADER = "leader"


class TieRule(str, Enum):
    BOTH_WIN = "both_win"
    NEITHER_WINS = "neither_wins"


class NextRoundStarter(str, Enum):
    ROUND_WINNER = "round_winner"
    ROUND_LOSER = "round_loser"
    ALTERNATE = "alternate"


class Phase(str, Enum):
    MULLIGAN = "mulligan"
    PLAYING = "playing"
    CHOOSING = "choosing"
    MATCH_OVER = "match_over"


class ChoiceKind(str, Enum):
    UNIT = "unit"
    ROW = "row"
    PLACE = "place"
    CARD = "card"


# --- phases of ADR 0009 ---------------------------------------------------------------------------

# The words phase C gave behaviour to — phase B carried them without acting on them.
PHASE_C_TRIGGERS = frozenset(
    {
        Trigger.ON_ACTIVATE,
        Trigger.ON_DESTROYED,
        Trigger.ON_TURN_START,
        Trigger.ON_TURN_END,
        Trigger.ON_ALLY_PLAYED,
        Trigger.ON_BOOSTED,
        Trigger.ON_DAMAGED,
    }
)
PHASE_C_ACTIONS = frozenset(
    {Action.PLAY_FROM_DECK, Action.PLAY_FROM_GRAVEYARD, Action.CREATE, Action.ADD_CHARGES}
)
PHASE_C_UNITS = frozenset(
    {Units.CHOSEN_ROW, Units.ADJACENT, Units.TRIGGER_UNIT, Units.PREVIOUS_TARGETS}
)


# --- definitions -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Where:
    """A filter over cards (cards.md §7.4). ``kind`` ``None`` means the selector's default."""

    kind: tuple[Kind, ...] | None = None
    color: Color | None = None
    tags_any: tuple[str, ...] = ()
    tags_none: tuple[str, ...] = ()
    statuses_any: tuple[Status, ...] = ()
    statuses_none: tuple[Status, ...] = ()
    same_id_as_this: bool = False
    power_at_least: int | None = None
    power_at_most: int | None = None
    stronger_than_this: bool = False
    boosted: bool = False
    damaged: bool = False


NO_FILTER = Where()


@dataclass(frozen=True)
class UnitTarget:
    units: Units
    side: Side | None = None
    rows: tuple[Row, ...] | None = None
    count: int = 1
    where: Where = NO_FILTER


@dataclass(frozen=True)
class RowTarget:
    pick: RowPick
    side: Side | None = None
    rows: tuple[Row, ...] | None = None


@dataclass(frozen=True)
class CardSource:
    pick: CardPick
    side: Side = Side.SELF
    count: int | None = None
    offer: int | None = None
    where: Where = NO_FILTER


@dataclass(frozen=True)
class CountCondition:
    count: int
    side: Side
    rows: tuple[Row, ...] | None = None
    where: Where = NO_FILTER


@dataclass(frozen=True)
class Conditions:
    on_row: Row | None = None
    trigger_unit: Where | None = None
    this: Where | None = None
    hand_at_most: int | None = None
    units_at_least: CountCondition | None = None
    starting_deck_without_neutral: bool = False


NO_CONDITIONS = Conditions()


@dataclass(frozen=True)
class Activation:
    """How a card's activated ability may be used (cards.md §6.3). ``charges`` ``None`` means
    unlimited."""

    charges: int | None
    cooldown: int = 0
    ready_on_play: bool = False


@dataclass(frozen=True)
class Ability:
    when: Trigger
    do: Action
    cond: Conditions = NO_CONDITIONS
    target: UnitTarget | None = None
    row_target: RowTarget | None = None
    cards: CardSource | None = None
    amount: int = 0
    count: int | None = None
    status: Status | None = None
    turns: int | None = None
    statuses: tuple[Status, ...] | None = None
    side: Side = Side.SELF
    card: str | None = None
    row: Row | None = None
    to: ChargeTarget | None = None
    effect: RowEffectKind | None = None
    scope: Scope | None = None
    only: RowEffectClass | None = None
    pool: Where | None = None
    offer: int | None = None


@dataclass(frozen=True)
class CardDef:
    id: str
    kind: Kind
    faction: str
    color: Color | None = None
    provisions: int = 0
    provision_bonus: int = 0
    token: bool = False
    power: int = 0
    armor: int = 0
    rows: tuple[Row, ...] = ()
    side: Side = Side.SELF
    statuses: tuple[Status, ...] = ()
    tags: tuple[str, ...] = ()
    activation: Activation | None = None
    abilities: tuple[Ability, ...] = ()

    @property
    def placed(self) -> bool:
        """Units and artifacts stand on a row; specials and leaders never do."""
        return self.kind in (Kind.UNIT, Kind.ARTIFACT)

    def triggered(self, when: Trigger) -> tuple[int, ...]:
        """Indices of abilities with the given trigger, in card order."""
        return tuple(i for i, a in enumerate(self.abilities) if a.when is when)

    def auras(self) -> tuple[Ability, ...]:
        return tuple(a for a in self.abilities if a.when is Trigger.WHILE_ON_BOARD)


Library = dict[str, CardDef]


@dataclass(frozen=True)
class Deck:
    """A deck: its cards, its leader and the stratagem it brings for going first (ADR 0011)."""

    faction: str
    cards: tuple[str, ...]
    leader: str
    stratagem: str


@dataclass(frozen=True)
class DeckProblem:
    """A deck-building rule a deck breaks (cards.md §12): the rule's key, the card it is about
    when there is one, and the numbers its message shows (``count``, ``min``, ``limit``, …)."""

    key: str
    card: str | None = None
    numbers: tuple[tuple[str, int], ...] = ()

    def __str__(self) -> str:
        return self.key if self.card is None else f"{self.key}:{self.card}"


@dataclass(frozen=True)
class Rules:
    """Every number that shapes a match or a deck (cards.md §4)."""

    rows: tuple[Row, ...] = (Row.MELEE, Row.RANGED)
    row_capacity: int = 9
    hand_limit: int = 10
    draws_per_round: tuple[int, ...] = (10, 3, 3)
    mulligans_per_round: tuple[int, ...] = (2, 2, 2)
    mulligans_per_skipped_draw: int = 1
    starter_extra_mulligans: int = 1
    starter_stratagem: bool = True
    rounds_to_win: int = 2
    max_rounds: int = 3
    tie_rule: TieRule = TieRule.BOTH_WIN
    next_round_starter: NextRoundStarter = NextRoundStarter.ROUND_WINNER
    deck_min_cards: int = 25
    deck_max_cards: int = 40
    deck_min_units: int = 13
    provision_base: int = 150
    copies_bronze: int = 2
    copies_gold: int = 1

    def draws(self, round_: int) -> int:
        return _per_round(self.draws_per_round, round_)

    def mulligans(self, round_: int) -> int:
        return _per_round(self.mulligans_per_round, round_)


def _per_round(values: tuple[int, ...], round_: int) -> int:
    if not values:
        return 0
    return values[min(round_, len(values)) - 1]


DEFAULT_RULES = Rules()


# --- building definitions from mappings -----------------------------------------------------------


def _rows(value: Sequence[str] | None) -> tuple[Row, ...] | None:
    return tuple(Row(r) for r in value) if value is not None else None


def where_from_mapping(m: Mapping[str, Any]) -> Where:
    return Where(
        kind=tuple(Kind(k) for k in m["kind"]) if "kind" in m else None,
        color=Color(m["color"]) if "color" in m else None,
        tags_any=tuple(str(t) for t in m.get("tags_any", ())),
        tags_none=tuple(str(t) for t in m.get("tags_none", ())),
        statuses_any=tuple(Status(s) for s in m.get("statuses_any", ())),
        statuses_none=tuple(Status(s) for s in m.get("statuses_none", ())),
        same_id_as_this=bool(m.get("same_id_as_this", False)),
        power_at_least=int(m["power_at_least"]) if "power_at_least" in m else None,
        power_at_most=int(m["power_at_most"]) if "power_at_most" in m else None,
        stronger_than_this=bool(m.get("stronger_than_this", False)),
        boosted=bool(m.get("boosted", False)),
        damaged=bool(m.get("damaged", False)),
    )


def _where(m: Mapping[str, Any] | None) -> Where:
    return where_from_mapping(m) if m is not None else NO_FILTER


def _unit_target(m: Mapping[str, Any]) -> UnitTarget:
    return UnitTarget(
        units=Units(m["units"]),
        side=Side(m["side"]) if "side" in m else None,
        rows=_rows(m.get("rows")),
        count=int(m.get("count", 1)),
        where=_where(m.get("where")),
    )


def _row_target(m: Mapping[str, Any]) -> RowTarget:
    return RowTarget(
        pick=RowPick(m["pick"]),
        side=Side(m["side"]) if "side" in m else None,
        rows=_rows(m.get("rows")),
    )


def _card_source(m: Mapping[str, Any]) -> CardSource:
    return CardSource(
        pick=CardPick(m["pick"]),
        side=Side(m.get("side", "self")),
        count=int(m["count"]) if "count" in m else None,
        offer=int(m["offer"]) if "offer" in m else None,
        where=_where(m.get("where")),
    )


def _conditions(m: Mapping[str, Any] | None) -> Conditions:
    if not m:
        return NO_CONDITIONS
    count = m.get("units_at_least")
    return Conditions(
        on_row=Row(m["on_row"]) if "on_row" in m else None,
        trigger_unit=where_from_mapping(m["trigger_unit"]) if "trigger_unit" in m else None,
        this=where_from_mapping(m["this"]) if "this" in m else None,
        hand_at_most=int(m["hand_at_most"]) if "hand_at_most" in m else None,
        units_at_least=(
            CountCondition(
                count=int(count["count"]),
                side=Side(count["side"]),
                rows=_rows(count.get("rows")),
                where=_where(count.get("where")),
            )
            if count is not None
            else None
        ),
        starting_deck_without_neutral=bool(m.get("starting_deck_without_neutral", False)),
    )


def _ability(m: Mapping[str, Any]) -> Ability:
    return Ability(
        when=Trigger(m["when"]),
        do=Action(m["do"]),
        cond=_conditions(m.get("if")),
        target=_unit_target(m["target"]) if "target" in m else None,
        row_target=_row_target(m["row_target"]) if "row_target" in m else None,
        cards=_card_source(m["cards"]) if "cards" in m else None,
        amount=int(m.get("amount", 0)),
        count=int(m["count"]) if "count" in m else None,
        status=Status(m["status"]) if "status" in m else None,
        turns=int(m["turns"]) if "turns" in m else None,
        statuses=tuple(Status(s) for s in m["statuses"]) if "statuses" in m else None,
        side=Side(m.get("side", "self")),
        card=str(m["card"]) if "card" in m else None,
        row=Row(m["row"]) if "row" in m else None,
        to=ChargeTarget(m["to"]) if "to" in m else None,
        effect=RowEffectKind(m["effect"]) if "effect" in m else None,
        scope=Scope(m["scope"]) if "scope" in m else None,
        only=RowEffectClass(m["only"]) if "only" in m else None,
        pool=where_from_mapping(m["pool"]) if "pool" in m else None,
        offer=int(m["offer"]) if "offer" in m else None,
    )


def _activation(m: Mapping[str, Any] | None) -> Activation | None:
    if m is None:
        return None
    cooldown = int(m.get("cooldown", 0))
    if "charges" in m:
        charges: int | None = int(m["charges"])
    else:
        charges = None if cooldown else 1
    return Activation(charges, cooldown, bool(m.get("ready_on_play", False)))


def card_def_from_mapping(card_id: str, faction: str, m: Mapping[str, Any]) -> CardDef:
    """Build a definition from a mapping shaped like one entry of a cards file."""
    kind = Kind(m["kind"])
    activation = _activation(m.get("activation"))
    if activation is None and kind is Kind.STRATAGEM:
        activation = Activation(charges=1)  # a stratagem is used once (ADR 0011)
    return CardDef(
        id=card_id,
        kind=kind,
        faction=faction,
        color=Color(m["color"]) if "color" in m else None,
        provisions=int(m.get("provisions", 0)),
        provision_bonus=int(m.get("provision_bonus", 0)),
        token=bool(m.get("token", False)),
        power=int(m.get("power", 0)),
        armor=int(m.get("armor", 0)),
        rows=tuple(Row(r) for r in m.get("rows", ())),
        side=Side(m.get("side", "self")),
        statuses=tuple(Status(s) for s in m.get("statuses", ())),
        tags=tuple(str(t) for t in m.get("tags", ())),
        activation=activation,
        abilities=tuple(_ability(a) for a in m.get("abilities", ())),
    )


def phase_c_words(defn: CardDef) -> list[str]:
    """The words of ``defn`` that ADR 0009 phase C gave behaviour to, as ``kind:word`` — the
    phase-B engine carried them without acting on them. A stratagem's activated ability acted
    from phase B on (ADR 0011) and is not listed."""
    words: list[str] = []
    stratagem = defn.kind is Kind.STRATAGEM  # its activated ability acts from phase B (ADR 0011)
    if defn.activation is not None and not stratagem:
        words.append("card:activation")
    for a in defn.abilities:
        if a.when in PHASE_C_TRIGGERS and not (stratagem and a.when is Trigger.ON_ACTIVATE):
            words.append(f"when:{a.when.value}")
        if a.do in PHASE_C_ACTIONS:
            words.append(f"do:{a.do.value}")
        if a.target is not None and a.target.units in PHASE_C_UNITS:
            words.append(f"units:{a.target.units.value}")
        if a.row_target is not None and a.row_target.pick is RowPick.CHOSEN:
            words.append("row_target:chosen")
        if a.cards is not None and a.cards.pick is CardPick.CHOSEN:
            words.append("cards:chosen")
        if a.cond.trigger_unit is not None:
            words.append("if:trigger_unit")
    return list(dict.fromkeys(words))


# --- match state -------------------------------------------------------------------------------


@dataclass
class StatusEntry:
    status: Status
    turns: int | None = None


@dataclass
class CardInstance:
    """One physical card. ``base``, ``power``, ``armor``, ``statuses``, ``charges`` and
    ``cooldown`` are its board state (cards.md §5), reset whenever it leaves the board.
    ``power`` is its current power without aura; ``charges`` ``None`` is unlimited."""

    instance: str
    card: str
    owner: int
    base: int = 0
    power: int = 0
    armor: int = 0
    statuses: list[StatusEntry] = field(default_factory=list)
    charges: int | None = None
    cooldown: int = 0

    def has(self, status: Status) -> bool:
        return any(e.status is status for e in self.statuses)

    def entry(self, status: Status) -> StatusEntry | None:
        for e in self.statuses:
            if e.status is status:
                return e
        return None

    def clone(self) -> CardInstance:
        return CardInstance(
            self.instance,
            self.card,
            self.owner,
            self.base,
            self.power,
            self.armor,
            [StatusEntry(e.status, e.turns) for e in self.statuses],
            self.charges,
            self.cooldown,
        )


@dataclass
class RowEffect:
    """A row-side's effect; ``since`` is the ``seq`` of the event that set it, which orders the
    per-turn effects of one player's row-sides (cards.md §10)."""

    effect: RowEffectKind
    amount: int
    count: int | None = None
    since: int = 0


@dataclass
class RowSide:
    """One row of one player: its cards left to right and at most one row effect."""

    cards: list[CardInstance] = field(default_factory=list)
    effect: RowEffect | None = None

    def clone(self) -> RowSide:
        effect = self.effect
        return RowSide(
            [c.clone() for c in self.cards],
            RowEffect(effect.effect, effect.amount, effect.count, effect.since) if effect else None,
        )


@dataclass
class MulliganState:
    """A player's redraws in the current round's mulligan; ``returned`` are the card ids sent
    back so far, which the replacement draws skip."""

    remaining: int
    used: int = 0
    done: bool = False
    returned: list[str] = field(default_factory=list)


@dataclass
class PlayerState:
    seat: int
    faction: str
    deck: list[CardInstance]
    hand: list[CardInstance]
    graveyard: list[CardInstance]
    banished: list[CardInstance]
    rows: dict[Row, RowSide]
    leader: CardInstance | None
    deck_had_neutral: bool = False
    passed: bool = False
    rounds_won: int = 0
    mulligan: MulliganState | None = None

    def clone(self) -> PlayerState:
        m = self.mulligan
        return PlayerState(
            seat=self.seat,
            faction=self.faction,
            deck=[c.clone() for c in self.deck],
            hand=[c.clone() for c in self.hand],
            graveyard=[c.clone() for c in self.graveyard],
            banished=[c.clone() for c in self.banished],
            rows={row: side.clone() for row, side in self.rows.items()},
            leader=self.leader.clone() if self.leader else None,
            deck_had_neutral=self.deck_had_neutral,
            passed=self.passed,
            rounds_won=self.rounds_won,
            mulligan=MulliganState(m.remaining, m.used, m.done, list(m.returned)) if m else None,
        )


@dataclass
class Invocation:
    """One ability of one card instance, waiting to be resolved on behalf of ``seat``.

    ``row`` is the row the card was played on, for its ``on_play`` abilities, or the row it was
    destroyed on, for its ``on_destroyed`` ones (``if.on_row`` §6.2, summons §8). ``trigger`` is
    the unit that fired ``on_ally_played``; ``previous`` what the ability before it, of the same
    card and trigger, acted on (``previous_targets``, §7.1) — set once that ability resolved."""

    instance: str
    card: str
    ability_index: int
    seat: int
    row: Row | None = None
    trigger: str | None = None
    previous: list[str] | None = None


@dataclass
class Placement:
    """A card an ability plays — ``play_from_deck``, ``play_from_graveyard``, ``create`` — waiting
    in the queue, ahead of the next ability, to be put on the board or, for a special, resolved
    (cards.md §8). It stays in its ``zone`` — ``deck`` or ``graveyard`` of ``zone_seat``, or
    ``created``: the resolving cards — until then. ``seat`` plays it; ``source`` is the card
    whose ability does."""

    instance: str
    card: str
    seat: int
    zone: str
    zone_seat: int
    source: str
    source_card: str


Step = Invocation | Placement


@dataclass(frozen=True)
class ChoiceOption:
    """One option of a pending choice (docs/protocol/match.md §7): a card — ``instance`` and
    ``card``, without an instance for a card ``create`` offers — a row-side (``seat``, ``row``),
    or a place on one (and ``position``)."""

    instance: str | None = None
    card: str | None = None
    seat: int | None = None
    row: Row | None = None
    position: int | None = None


@dataclass
class PendingChoice:
    """A pick the core waits for. ``step`` is the ability that asks, or the card being placed
    for a choice of kind ``place``. ``queue`` is the rest of the resolution queue, which resolves
    once the pick is made (§11.3). ``order`` is the card whose activated ability is resolving,
    if any, and ``order_started`` whether it has spent its charge yet — until then the choice
    may be cancelled (cards.md §6.3). Without an ``order`` a played card is resolving.
    ``resolved`` counts the steps the resolution has resolved so far (§11.3)."""

    seat: int
    kind: ChoiceKind
    step: Step
    prompt_key: str
    options: list[ChoiceOption]
    queue: list[Step]
    cancellable: bool = False
    order: str | None = None
    order_started: bool = False
    resolved: int = 0


@dataclass
class RoundResult:
    round: int
    winners: tuple[int, ...]
    scores: tuple[int, int]


@dataclass
class MatchState:
    """A match in progress. ``turn`` is whose turn it is (``None`` during the mulligan and after
    the match); ``active`` is the player whose turn it is or who took the last one, which is the
    side board order starts from (cards.md §5). ``played`` and ``ordered`` say whether the turn's
    card has been played and whether an activated ability has been used this turn (§11.4)."""

    rules: Rules
    seed: str
    rng_block: int
    rng_pos: int
    next_instance: int
    phase: Phase
    round: int
    starter: int
    turn: int | None
    active: int
    players: list[PlayerState]
    seq: int
    winner: int | None
    pending: PendingChoice | None
    resolving: list[CardInstance]
    rounds: list[RoundResult]
    played: bool = False
    ordered: bool = False

    def other(self, seat: int) -> int:
        return 1 - seat

    def clone(self) -> MatchState:
        p = self.pending
        return MatchState(
            rules=self.rules,
            seed=self.seed,
            rng_block=self.rng_block,
            rng_pos=self.rng_pos,
            next_instance=self.next_instance,
            phase=self.phase,
            round=self.round,
            starter=self.starter,
            turn=self.turn,
            active=self.active,
            players=[pl.clone() for pl in self.players],
            seq=self.seq,
            winner=self.winner,
            pending=(
                PendingChoice(
                    p.seat,
                    p.kind,
                    _clone_step(p.step),
                    p.prompt_key,
                    list(p.options),
                    [_clone_step(i) for i in p.queue],
                    p.cancellable,
                    p.order,
                    p.order_started,
                    p.resolved,
                )
                if p
                else None
            ),
            resolving=[c.clone() for c in self.resolving],
            rounds=[RoundResult(r.round, r.winners, r.scores) for r in self.rounds],
            played=self.played,
            ordered=self.ordered,
        )


def _clone_step(step: Step) -> Step:
    if isinstance(step, Placement):
        return Placement(
            step.instance,
            step.card,
            step.seat,
            step.zone,
            step.zone_seat,
            step.source,
            step.source_card,
        )
    return _clone_invocation(step)


def _clone_invocation(inv: Invocation) -> Invocation:
    return Invocation(
        inv.instance,
        inv.card,
        inv.ability_index,
        inv.seat,
        inv.row,
        inv.trigger,
        list(inv.previous) if inv.previous is not None else None,
    )
