"""Canonical serialisation of match state: the same state always gives the same bytes."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .model import (
    CardInstance,
    ChoiceKind,
    Deck,
    Invocation,
    MatchState,
    MulliganState,
    NextRoundStarter,
    PendingChoice,
    Phase,
    PlayerState,
    RoundResult,
    Row,
    RowEffect,
    RowEffectKind,
    RowSide,
    Rules,
    Status,
    StatusEntry,
    TieRule,
)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _instance_to_dict(u: CardInstance) -> dict[str, Any]:
    return {
        "instance": u.instance,
        "card": u.card,
        "owner": u.owner,
        "base": u.base,
        "power": u.power,
        "armor": u.armor,
        "statuses": [{"status": e.status.value, "turns": e.turns} for e in u.statuses],
        "charges": u.charges,
        "cooldown": u.cooldown,
    }


def _instance_from_dict(d: dict[str, Any]) -> CardInstance:
    return CardInstance(
        instance=str(d["instance"]),
        card=str(d["card"]),
        owner=int(d["owner"]),
        base=int(d["base"]),
        power=int(d["power"]),
        armor=int(d["armor"]),
        statuses=[
            StatusEntry(Status(e["status"]), None if e["turns"] is None else int(e["turns"]))
            for e in d["statuses"]
        ],
        charges=None if d["charges"] is None else int(d["charges"]),
        cooldown=int(d["cooldown"]),
    )


def _invocation_to_dict(inv: Invocation) -> dict[str, Any]:
    return {
        "instance": inv.instance,
        "card": inv.card,
        "ability_index": inv.ability_index,
        "seat": inv.seat,
        "row": inv.row.value if inv.row is not None else None,
        "trigger": inv.trigger,
        "previous": list(inv.previous) if inv.previous is not None else None,
    }


def _invocation_from_dict(d: dict[str, Any]) -> Invocation:
    previous = d["previous"]
    return Invocation(
        str(d["instance"]),
        str(d["card"]),
        int(d["ability_index"]),
        int(d["seat"]),
        Row(d["row"]) if d["row"] is not None else None,
        None if d["trigger"] is None else str(d["trigger"]),
        None if previous is None else [str(i) for i in previous],
    )


def _row_to_dict(side: RowSide) -> dict[str, Any]:
    effect = side.effect
    return {
        "cards": [_instance_to_dict(u) for u in side.cards],
        "effect": (
            {
                "effect": effect.effect.value,
                "amount": effect.amount,
                "count": effect.count,
                "since": effect.since,
            }
            if effect is not None
            else None
        ),
    }


def _row_from_dict(d: dict[str, Any]) -> RowSide:
    e = d["effect"]
    return RowSide(
        cards=[_instance_from_dict(u) for u in d["cards"]],
        effect=(
            RowEffect(
                RowEffectKind(e["effect"]),
                int(e["amount"]),
                None if e["count"] is None else int(e["count"]),
                int(e["since"]),
            )
            if e is not None
            else None
        ),
    )


def _player_to_dict(p: PlayerState) -> dict[str, Any]:
    m = p.mulligan
    return {
        "seat": p.seat,
        "faction": p.faction,
        "deck": [_instance_to_dict(u) for u in p.deck],
        "hand": [_instance_to_dict(u) for u in p.hand],
        "graveyard": [_instance_to_dict(u) for u in p.graveyard],
        "banished": [_instance_to_dict(u) for u in p.banished],
        "rows": {row.value: _row_to_dict(side) for row, side in p.rows.items()},
        "leader": _instance_to_dict(p.leader) if p.leader else None,
        "deck_had_neutral": p.deck_had_neutral,
        "passed": p.passed,
        "rounds_won": p.rounds_won,
        "mulligan": (
            {"remaining": m.remaining, "used": m.used, "done": m.done, "returned": m.returned}
            if m is not None
            else None
        ),
    }


def _player_from_dict(d: dict[str, Any], rules: Rules) -> PlayerState:
    m = d["mulligan"]
    return PlayerState(
        seat=int(d["seat"]),
        faction=str(d["faction"]),
        deck=[_instance_from_dict(u) for u in d["deck"]],
        hand=[_instance_from_dict(u) for u in d["hand"]],
        graveyard=[_instance_from_dict(u) for u in d["graveyard"]],
        banished=[_instance_from_dict(u) for u in d["banished"]],
        rows={row: _row_from_dict(d["rows"][row.value]) for row in rules.rows},
        leader=_instance_from_dict(d["leader"]) if d.get("leader") else None,
        deck_had_neutral=bool(d["deck_had_neutral"]),
        passed=bool(d["passed"]),
        rounds_won=int(d["rounds_won"]),
        mulligan=(
            MulliganState(
                remaining=int(m["remaining"]),
                used=int(m["used"]),
                done=bool(m["done"]),
                returned=[str(c) for c in m["returned"]],
            )
            if m is not None
            else None
        ),
    )


def rules_to_dict(rules: Rules) -> dict[str, Any]:
    return {
        "rows": [r.value for r in rules.rows],
        "row_capacity": rules.row_capacity,
        "hand_limit": rules.hand_limit,
        "draws_per_round": list(rules.draws_per_round),
        "mulligans_per_round": list(rules.mulligans_per_round),
        "mulligans_per_skipped_draw": rules.mulligans_per_skipped_draw,
        "starter_extra_mulligans": rules.starter_extra_mulligans,
        "starter_stratagem": rules.starter_stratagem,
        "rounds_to_win": rules.rounds_to_win,
        "max_rounds": rules.max_rounds,
        "tie_rule": rules.tie_rule.value,
        "next_round_starter": rules.next_round_starter.value,
        "deck_min_cards": rules.deck_min_cards,
        "deck_max_cards": rules.deck_max_cards,
        "deck_min_units": rules.deck_min_units,
        "provision_base": rules.provision_base,
        "copies_bronze": rules.copies_bronze,
        "copies_gold": rules.copies_gold,
    }


def rules_from_dict(d: dict[str, Any]) -> Rules:
    """A ``Rules`` value from its dictionary; every field is required, so a record keeps
    replaying the same way when a default changes."""
    return Rules(
        rows=tuple(Row(r) for r in d["rows"]),
        row_capacity=int(d["row_capacity"]),
        hand_limit=int(d["hand_limit"]),
        draws_per_round=tuple(int(n) for n in d["draws_per_round"]),
        mulligans_per_round=tuple(int(n) for n in d["mulligans_per_round"]),
        mulligans_per_skipped_draw=int(d["mulligans_per_skipped_draw"]),
        starter_extra_mulligans=int(d["starter_extra_mulligans"]),
        starter_stratagem=bool(d["starter_stratagem"]),
        rounds_to_win=int(d["rounds_to_win"]),
        max_rounds=int(d["max_rounds"]),
        tie_rule=TieRule(d["tie_rule"]),
        next_round_starter=NextRoundStarter(d["next_round_starter"]),
        deck_min_cards=int(d["deck_min_cards"]),
        deck_max_cards=int(d["deck_max_cards"]),
        deck_min_units=int(d["deck_min_units"]),
        provision_base=int(d["provision_base"]),
        copies_bronze=int(d["copies_bronze"]),
        copies_gold=int(d["copies_gold"]),
    )


def deck_to_dict(deck: Deck) -> dict[str, Any]:
    return {
        "faction": deck.faction,
        "leader": deck.leader,
        "stratagem": deck.stratagem,
        "cards": list(deck.cards),
    }


def deck_from_dict(d: dict[str, Any]) -> Deck:
    return Deck(
        str(d["faction"]),
        tuple(str(c) for c in d["cards"]),
        str(d["leader"]),
        str(d["stratagem"]),
    )


def _pending_to_dict(p: PendingChoice) -> dict[str, Any]:
    return {
        "seat": p.seat,
        "kind": p.kind.value,
        "invocation": _invocation_to_dict(p.invocation),
        "prompt_key": p.prompt_key,
        "options": list(p.options),
        "queue": [_invocation_to_dict(i) for i in p.queue],
        "cancellable": p.cancellable,
        "order": p.order,
        "order_started": p.order_started,
    }


def _pending_from_dict(d: dict[str, Any]) -> PendingChoice:
    return PendingChoice(
        seat=int(d["seat"]),
        kind=ChoiceKind(d["kind"]),
        invocation=_invocation_from_dict(d["invocation"]),
        prompt_key=str(d["prompt_key"]),
        options=[str(o) for o in d["options"]],
        queue=[_invocation_from_dict(i) for i in d["queue"]],
        cancellable=bool(d["cancellable"]),
        order=None if d["order"] is None else str(d["order"]),
        order_started=bool(d["order_started"]),
    )


def state_to_dict(s: MatchState) -> dict[str, Any]:
    return {
        "rules": rules_to_dict(s.rules),
        "seed": s.seed,
        "rng_block": s.rng_block,
        "rng_pos": s.rng_pos,
        "next_instance": s.next_instance,
        "phase": s.phase.value,
        "round": s.round,
        "starter": s.starter,
        "turn": s.turn,
        "active": s.active,
        "players": [_player_to_dict(p) for p in s.players],
        "seq": s.seq,
        "winner": s.winner,
        "pending": _pending_to_dict(s.pending) if s.pending is not None else None,
        "resolving": [_instance_to_dict(u) for u in s.resolving],
        "rounds": [
            {"round": r.round, "winners": list(r.winners), "scores": list(r.scores)}
            for r in s.rounds
        ],
        "played": s.played,
        "ordered": s.ordered,
    }


def state_from_dict(d: dict[str, Any]) -> MatchState:
    rules = rules_from_dict(d["rules"])
    return MatchState(
        rules=rules,
        seed=str(d["seed"]),
        rng_block=int(d["rng_block"]),
        rng_pos=int(d["rng_pos"]),
        next_instance=int(d["next_instance"]),
        phase=Phase(d["phase"]),
        round=int(d["round"]),
        starter=int(d["starter"]),
        turn=None if d["turn"] is None else int(d["turn"]),
        active=int(d["active"]),
        players=[_player_from_dict(p, rules) for p in d["players"]],
        seq=int(d["seq"]),
        winner=None if d["winner"] is None else int(d["winner"]),
        pending=_pending_from_dict(d["pending"]) if d["pending"] is not None else None,
        resolving=[_instance_from_dict(u) for u in d["resolving"]],
        rounds=[
            RoundResult(
                int(r["round"]),
                tuple(int(w) for w in r["winners"]),
                (int(r["scores"][0]), int(r["scores"][1])),
            )
            for r in d["rounds"]
        ],
        played=bool(d["played"]),
        ordered=bool(d["ordered"]),
    )


def state_hash(s: MatchState) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(state_to_dict(s)).encode("utf-8")).hexdigest()
