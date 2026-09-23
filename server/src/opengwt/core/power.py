"""Power, aura, scores and board order — docs/protocol/cards.md §5 and §11.1.

``power = current + aura``: the current power a unit carries (its base, raised by boosts and
lowered by damage) plus the continuous boosts of the other cards on its row-side, recomputed on
every read and never stored. Artifacts have no power.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Action, CardInstance, Kind, Library, MatchState, Row, Scope, Status


@dataclass(frozen=True)
class Loc:
    """Where a card stands on the board: its controller's seat, the row and the index."""

    seat: int
    row: Row
    index: int
    card: CardInstance


def is_unit(lib: Library, card: CardInstance) -> bool:
    return lib[card.card].kind is Kind.UNIT


def aura_at(lib: Library, state: MatchState, seat: int, row: Row, index: int) -> int:
    cards = state.players[seat].rows[row].cards
    total = 0
    for j, other in enumerate(cards):
        if j == index or other.has(Status.LOCKED):
            continue
        for ability in lib[other.card].auras():
            if ability.do is not Action.CONTINUOUS_BOOST:
                continue
            if ability.scope is Scope.ROW or (
                ability.scope is Scope.ADJACENT and abs(j - index) == 1
            ):
                total += ability.amount
    return total


def power_at(lib: Library, state: MatchState, seat: int, row: Row, index: int) -> int:
    """The power of the card at a board position; 0 for an artifact."""
    card = state.players[seat].rows[row].cards[index]
    if not is_unit(lib, card):
        return 0
    return card.power + aura_at(lib, state, seat, row, index)


def board(state: MatchState, first: int | None = None) -> list[Loc]:
    """Every card on the board in board order: the side of ``first`` (by default the active
    player) first, rows in ``Rules.rows`` order, left to right."""
    start = state.active if first is None else first
    out: list[Loc] = []
    for seat in (start, 1 - start):
        for row in state.rules.rows:
            out.extend(
                Loc(seat, row, i, c) for i, c in enumerate(state.players[seat].rows[row].cards)
            )
    return out


def score(lib: Library, state: MatchState, seat: int) -> int:
    total = 0
    for row in state.rules.rows:
        for index in range(len(state.players[seat].rows[row].cards)):
            total += power_at(lib, state, seat, row, index)
    return total
