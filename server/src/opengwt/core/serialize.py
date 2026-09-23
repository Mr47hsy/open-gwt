"""Canonical serialisation of match state: the same state always gives the same bytes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from .model import (
    ROWS,
    CardInstance,
    Deck,
    Invocation,
    MatchState,
    PendingChoice,
    Phase,
    PlayerState,
    RoundResult,
    Row,
    RowEffect,
    RowState,
    Rules,
)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _instance_to_dict(u: CardInstance) -> dict[str, Any]:
    return {"instance": u.instance, "card": u.card, "owner": u.owner, "power": u.power}


def _instance_from_dict(d: dict[str, Any]) -> CardInstance:
    return CardInstance(str(d["instance"]), str(d["card"]), int(d["owner"]), int(d["power"]))


def _invocation_to_dict(inv: Invocation) -> dict[str, Any]:
    return {
        "instance": inv.instance,
        "card": inv.card,
        "ability_index": inv.ability_index,
        "seat": inv.seat,
    }


def _invocation_from_dict(d: dict[str, Any]) -> Invocation:
    return Invocation(str(d["instance"]), str(d["card"]), int(d["ability_index"]), int(d["seat"]))


def _row_to_dict(row_state: RowState) -> dict[str, Any]:
    return {
        "effects": [e.value for e in row_state.effects],
        "units": [_instance_to_dict(u) for u in row_state.units],
    }


def _player_to_dict(p: PlayerState) -> dict[str, Any]:
    return {
        "seat": p.seat,
        "faction": p.faction,
        "deck": [_instance_to_dict(u) for u in p.deck],
        "hand": [_instance_to_dict(u) for u in p.hand],
        "discard": [_instance_to_dict(u) for u in p.discard],
        "rows": {row.value: _row_to_dict(p.rows[row]) for row in ROWS},
        "leader": _instance_to_dict(p.leader) if p.leader else None,
        "leader_used": p.leader_used,
        "passed": p.passed,
        "lives": p.lives,
        "rounds_won": p.rounds_won,
        "mulligan_done": p.mulligan_done,
    }


def _player_from_dict(d: dict[str, Any]) -> PlayerState:
    rows: dict[Row, RowState] = {}
    for row in ROWS:
        rd = d["rows"][row.value]
        rows[row] = RowState(
            effects=[RowEffect(e) for e in rd["effects"]],
            units=[_instance_from_dict(u) for u in rd["units"]],
        )
    return PlayerState(
        seat=int(d["seat"]),
        faction=str(d["faction"]),
        deck=[_instance_from_dict(u) for u in d["deck"]],
        hand=[_instance_from_dict(u) for u in d["hand"]],
        discard=[_instance_from_dict(u) for u in d["discard"]],
        rows=rows,
        leader=_instance_from_dict(d["leader"]) if d.get("leader") else None,
        leader_used=bool(d["leader_used"]),
        passed=bool(d["passed"]),
        lives=int(d["lives"]),
        rounds_won=int(d["rounds_won"]),
        mulligan_done=bool(d["mulligan_done"]),
    )


def rules_to_dict(rules: Rules) -> dict[str, Any]:
    return asdict(rules)


def rules_from_dict(d: dict[str, Any]) -> Rules:
    return Rules(**{k: int(v) for k, v in d.items()})


def deck_to_dict(deck: Deck) -> dict[str, Any]:
    return {"faction": deck.faction, "leader": deck.leader, "cards": list(deck.cards)}


def deck_from_dict(d: dict[str, Any]) -> Deck:
    return Deck(str(d["faction"]), tuple(str(c) for c in d["cards"]), d.get("leader"))


def state_to_dict(s: MatchState) -> dict[str, Any]:
    pending: dict[str, Any] | None = None
    if s.pending is not None:
        pending = {
            "seat": s.pending.seat,
            "invocation": _invocation_to_dict(s.pending.invocation),
            "prompt_key": s.pending.prompt_key,
            "options": list(s.pending.options),
            "queue": [_invocation_to_dict(i) for i in s.pending.queue],
        }
    return {
        "rules": rules_to_dict(s.rules),
        "seed": s.seed,
        "rng_state": s.rng_state,
        "rng_inc": s.rng_inc,
        "phase": s.phase.value,
        "round": s.round,
        "starter": s.starter,
        "turn": s.turn,
        "mulligan_seat": s.mulligan_seat,
        "players": [_player_to_dict(p) for p in s.players],
        "next_instance": s.next_instance,
        "seq": s.seq,
        "winner": s.winner,
        "pending": pending,
        "resolving": [_instance_to_dict(u) for u in s.resolving],
        "rounds": [
            {"round": r.round, "winner": r.winner, "scores": list(r.scores)} for r in s.rounds
        ],
    }


def state_from_dict(d: dict[str, Any]) -> MatchState:
    pending: PendingChoice | None = None
    if d.get("pending") is not None:
        pd = d["pending"]
        pending = PendingChoice(
            seat=int(pd["seat"]),
            invocation=_invocation_from_dict(pd["invocation"]),
            prompt_key=str(pd["prompt_key"]),
            options=[str(o) for o in pd["options"]],
            queue=[_invocation_from_dict(i) for i in pd["queue"]],
        )
    return MatchState(
        rules=rules_from_dict(d["rules"]),
        seed=int(d["seed"]),
        rng_state=int(d["rng_state"]),
        rng_inc=int(d["rng_inc"]),
        phase=Phase(d["phase"]),
        round=int(d["round"]),
        starter=int(d["starter"]),
        turn=d["turn"],
        mulligan_seat=d["mulligan_seat"],
        players=[_player_from_dict(p) for p in d["players"]],
        next_instance=int(d["next_instance"]),
        seq=int(d["seq"]),
        winner=d["winner"],
        pending=pending,
        resolving=[_instance_from_dict(u) for u in d["resolving"]],
        rounds=[
            RoundResult(int(r["round"]), r["winner"], (int(r["scores"][0]), int(r["scores"][1])))
            for r in d["rounds"]
        ],
    )


def state_hash(s: MatchState) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(state_to_dict(s)).encode("utf-8")).hexdigest()
