"""Intents: what a player asks the rules to do. Exactly the shapes of docs/protocol/match.md §6."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import Row


@dataclass(frozen=True)
class Mulligan:
    cards: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlayCard:
    card: str
    row: Row | None = None


@dataclass(frozen=True)
class UseLeader:
    pass


@dataclass(frozen=True)
class Pass:
    pass


@dataclass(frozen=True)
class Choose:
    option: int


Intent = Mulligan | PlayCard | UseLeader | Pass | Choose

_KINDS: dict[type, str] = {
    Mulligan: "mulligan",
    PlayCard: "play_card",
    UseLeader: "use_leader",
    Pass: "pass",
    Choose: "choose",
}


def intent_kind(intent: Intent) -> str:
    return _KINDS[type(intent)]


def intent_to_dict(intent: Intent) -> dict[str, Any]:
    d: dict[str, Any] = {"kind": intent_kind(intent)}
    if isinstance(intent, Mulligan):
        d["cards"] = list(intent.cards)
    elif isinstance(intent, PlayCard):
        d["card"] = intent.card
        if intent.row is not None:
            d["row"] = intent.row.value
    elif isinstance(intent, Choose):
        d["option"] = intent.option
    return d


def intent_from_dict(d: dict[str, Any]) -> Intent:
    kind = d["kind"]
    if kind == "mulligan":
        return Mulligan(tuple(d.get("cards", ())))
    if kind == "play_card":
        return PlayCard(d["card"], Row(d["row"]) if d.get("row") is not None else None)
    if kind == "use_leader":
        return UseLeader()
    if kind == "pass":
        return Pass()
    if kind == "choose":
        return Choose(int(d["option"]))
    raise ValueError(f"unknown intent kind {kind!r}")
