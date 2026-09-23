"""Effective power, row totals and scores — docs/protocol/cards.md §6."""

from __future__ import annotations

from .model import ROWS, Action, CardInstance, Kind, Library, MatchState, Row, RowEffect


def effective_power(
    lib: Library, state: MatchState, seat: int, row: Row, unit: CardInstance
) -> int:
    defn = lib[unit.card]
    if defn.kind is not Kind.UNIT:
        return 0
    power = unit.power
    if defn.immune:
        return power
    row_state = state.players[seat].rows[row]
    if RowEffect.POWER_TO_ONE in row_state.effects:
        power = 1
    if defn.passives(Action.MULTIPLY_POWER_BY_COPIES):
        power *= sum(1 for u in row_state.units if u.card == unit.card)
    for other in row_state.units:
        if other is unit:
            continue
        for passive in lib[other.card].passives(Action.BOOST_ROW_OTHERS):
            power += passive.amount
    if RowEffect.DOUBLE_POWER in row_state.effects:
        power *= 2
    return power


def row_total(lib: Library, state: MatchState, seat: int, row: Row) -> int:
    return sum(
        effective_power(lib, state, seat, row, u) for u in state.players[seat].rows[row].units
    )


def score(lib: Library, state: MatchState, seat: int) -> int:
    return sum(row_total(lib, state, seat, row) for row in ROWS)


def board_powers(lib: Library, state: MatchState) -> dict[str, tuple[int, int]]:
    """``instance -> (seat, effective power)`` for every card on the board, in board order."""
    out: dict[str, tuple[int, int]] = {}
    for seat in (0, 1):
        for row in ROWS:
            for unit in state.players[seat].rows[row].units:
                out[unit.instance] = (seat, effective_power(lib, state, seat, row, unit))
    return out
