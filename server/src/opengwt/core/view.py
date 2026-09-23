"""Per-player projection of a match — docs/protocol/match.md §7. Hidden information is removed
here, before anything is serialised; nothing else produces client-facing state."""

from __future__ import annotations

from typing import Any

from .engine import legal_intents, order_ready
from .intents import intent_to_dict
from .model import CardInstance, Kind, Library, MatchState, Phase, PlayerState
from .power import aura_at, board, power_at, score

PROTOCOL = 2


def _card(inst: CardInstance) -> dict[str, Any]:
    return {"instance": inst.instance, "card": inst.card}


def _order(
    lib: Library, state: MatchState, seat: int, inst: CardInstance, viewer: int
) -> dict[str, Any] | None:
    """``ready`` is only ever true for the viewer's own cards on their turn (match.md §7)."""
    if lib[inst.card].activation is None:
        return None
    return {
        "ready": seat == viewer and order_ready(lib, state, seat, inst),
        "charges": inst.charges,
        "cooldown": inst.cooldown,
    }


def _statuses(inst: CardInstance) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in inst.statuses:
        entry: dict[str, Any] = {"status": e.status.value}
        if e.turns is not None:
            entry["turns"] = e.turns
        out.append(entry)
    return out


def _rows(lib: Library, state: MatchState, player: PlayerState, viewer: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in state.rules.rows:
        side = player.rows[row]
        cards: list[dict[str, Any]] = []
        for index, c in enumerate(side.cards):
            entry: dict[str, Any] = {"instance": c.instance, "card": c.card, "owner": c.owner}
            if lib[c.card].kind is Kind.UNIT:
                entry["power"] = power_at(lib, state, player.seat, row, index)
                entry["base"] = c.base
                entry["aura"] = aura_at(lib, state, player.seat, row, index)
                entry["armor"] = c.armor
            entry["statuses"] = _statuses(c)
            entry["order"] = _order(lib, state, player.seat, c, viewer)
            cards.append(entry)
        effect = side.effect
        effect_view: dict[str, Any] | None = None
        if effect is not None:
            effect_view = {"effect": effect.effect.value, "amount": effect.amount}
            if effect.count is not None:
                effect_view["count"] = effect.count
        out[row.value] = {"effect": effect_view, "cards": cards}
    return out


def _common(lib: Library, state: MatchState, player: PlayerState, viewer: int) -> dict[str, Any]:
    leader = player.leader
    m = player.mulligan
    return {
        "seat": player.seat,
        "faction": player.faction,
        "score": score(lib, state, player.seat),
        "rounds_won": player.rounds_won,
        "passed": player.passed,
        "hand_count": len(player.hand),
        "deck_count": len(player.deck),
        "graveyard": [_card(u) for u in player.graveyard],
        "banished": [_card(u) for u in player.banished],
        "leader": (
            {**_card(leader), "order": _order(lib, state, player.seat, leader, viewer)}
            if leader is not None
            else None
        ),
        "mulligan": {"remaining": m.remaining, "done": m.done} if m is not None else None,
        "rows": _rows(lib, state, player, viewer),
    }


def _pending(state: MatchState, seat: int) -> dict[str, Any] | None:
    pending = state.pending
    if pending is None or pending.seat != seat:
        return None
    by_id = {loc.card.instance: loc for loc in board(state, seat)}
    options = []
    for iid in pending.options:
        loc = by_id[iid]
        options.append(
            {
                "side": "me" if loc.seat == seat else "opponent",
                "row": loc.row.value,
                "position": loc.index,
                "instance": iid,
                "card": loc.card.card,
            }
        )
    return {
        "kind": pending.kind.value,
        "prompt_key": pending.prompt_key,
        "source": {"instance": pending.invocation.instance, "card": pending.invocation.card},
        "cancellable": pending.cancellable,
        "options": options,
    }


def player_view(
    lib: Library, state: MatchState, seat: int, match_id: str | None = None
) -> dict[str, Any]:
    me = state.players[seat]
    opponent = state.players[state.other(seat)]
    mine = _common(lib, state, me, seat)
    mine["hand"] = [_card(u) for u in me.hand]
    theirs = _common(lib, state, opponent, seat)

    turn: str | None = None
    if state.turn is not None:
        turn = "me" if state.turn == seat else "opponent"
    winner: str | None = None
    if state.phase is Phase.MATCH_OVER:
        winner = "draw" if state.winner is None else "me" if state.winner == seat else "opponent"

    view: dict[str, Any] = {"protocol": PROTOCOL}
    if match_id is not None:
        view["match_id"] = match_id
    view.update(
        {
            "seq": state.seq,
            "phase": state.phase.value,
            "round": state.round,
            "turn": turn,
            "winner": winner,
            "me": mine,
            "opponent": theirs,
            "legal_intents": [intent_to_dict(i) for i in legal_intents(lib, state, seat)],
            "pending_choice": _pending(state, seat),
        }
    )
    return view
