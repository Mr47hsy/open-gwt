"""Per-player projection of a match — docs/protocol/match.md §7. Hidden information is removed
here, before anything is serialised; nothing else produces client-facing state."""

from __future__ import annotations

from typing import Any

from .engine import legal_intents
from .intents import intent_to_dict
from .model import ROWS, CardInstance, Library, MatchState, Phase, PlayerState
from .power import effective_power, score


def _card(inst: CardInstance) -> dict[str, Any]:
    return {"instance": inst.instance, "card": inst.card}


def _rows(lib: Library, state: MatchState, player: PlayerState) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in ROWS:
        row_state = player.rows[row]
        out[row.value] = {
            "effects": [e.value for e in row_state.effects],
            "units": [
                {
                    "instance": u.instance,
                    "card": u.card,
                    "owner": u.owner,
                    "power": effective_power(lib, state, player.seat, row, u),
                    "base": u.power,
                }
                for u in row_state.units
            ],
        }
    return out


def _common(lib: Library, state: MatchState, player: PlayerState) -> dict[str, Any]:
    leader = player.leader
    return {
        "seat": player.seat,
        "faction": player.faction,
        "score": score(lib, state, player.seat),
        "lives": player.lives,
        "rounds_won": player.rounds_won,
        "passed": player.passed,
        "deck_count": len(player.deck),
        "discard": [_card(u) for u in player.discard],
        "leader": {"card": leader.card, "used": player.leader_used} if leader else None,
        "rows": _rows(lib, state, player),
        "mulligan_done": player.mulligan_done,
    }


def player_view(lib: Library, state: MatchState, seat: int) -> dict[str, Any]:
    me = state.players[seat]
    opponent = state.players[state.other(seat)]
    mine = _common(lib, state, me)
    mine["hand"] = [_card(u) for u in me.hand]
    theirs = _common(lib, state, opponent)
    theirs["hand_count"] = len(opponent.hand)

    if state.turn is None:
        turn: str | None = None
    else:
        turn = "me" if state.turn == seat else "opponent"

    pending = state.pending
    pending_view: dict[str, Any] | None = None
    if pending is not None and pending.seat == seat:
        by_id = {u.instance: u for p in state.players for u in _all_cards(p)}
        pending_view = {
            "prompt_key": pending.prompt_key,
            "options": [_card(by_id[i]) for i in pending.options if i in by_id],
        }

    winner: str | None = None
    if state.phase is Phase.MATCH_OVER:
        winner = "draw" if state.winner is None else "me" if state.winner == seat else "opponent"

    return {
        "protocol": 1,
        "seq": state.seq,
        "phase": state.phase.value,
        "round": state.round,
        "turn": turn,
        "me": mine,
        "opponent": theirs,
        "mulligan": (
            {"seat": state.mulligan_seat, "max": state.rules.mulligan_max}
            if state.phase is Phase.MULLIGAN
            else None
        ),
        "legal_intents": [intent_to_dict(i) for i in legal_intents(lib, state, seat)],
        "pending_choice": pending_view,
        "winner": winner,
    }


def _all_cards(player: PlayerState) -> list[CardInstance]:
    cards = list(player.deck) + list(player.hand) + list(player.discard)
    for row in ROWS:
        cards.extend(player.rows[row].units)
    if player.leader is not None:
        cards.append(player.leader)
    return cards
