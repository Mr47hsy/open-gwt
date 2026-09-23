"""Intents: what a player asks the rules to do. Exactly the shapes of docs/protocol/match.md §6."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import Row


@dataclass(frozen=True)
class Mulligan:
    """Return one card from hand to the deck and draw a replacement."""

    card: str


@dataclass(frozen=True)
class EndMulligan:
    pass


@dataclass(frozen=True)
class PlayCard:
    """``row`` and ``position`` for a unit or artifact, neither for a special. In
    ``legal_intents`` a play without ``position`` stands for every position on that row-side."""

    card: str
    row: Row | None = None
    position: int | None = None


@dataclass(frozen=True)
class UseOrder:
    instance: str


@dataclass(frozen=True)
class Pass:
    pass


@dataclass(frozen=True)
class Choose:
    option: int


@dataclass(frozen=True)
class CancelChoice:
    pass


Intent = Mulligan | EndMulligan | PlayCard | UseOrder | Pass | Choose | CancelChoice

_KINDS: dict[type, str] = {
    Mulligan: "mulligan",
    EndMulligan: "end_mulligan",
    PlayCard: "play_card",
    UseOrder: "use_order",
    Pass: "pass",
    Choose: "choose",
    CancelChoice: "cancel_choice",
}


def intent_kind(intent: Intent) -> str:
    return _KINDS[type(intent)]


def intent_to_dict(intent: Intent) -> dict[str, Any]:
    d: dict[str, Any] = {"kind": intent_kind(intent)}
    if isinstance(intent, Mulligan):
        d["card"] = intent.card
    elif isinstance(intent, PlayCard):
        d["card"] = intent.card
        if intent.row is not None:
            d["row"] = intent.row.value
        if intent.position is not None:
            d["position"] = intent.position
    elif isinstance(intent, UseOrder):
        d["instance"] = intent.instance
    elif isinstance(intent, Choose):
        d["option"] = intent.option
    return d


def intent_from_dict(d: dict[str, Any]) -> Intent:
    kind = d["kind"]
    if kind == "mulligan":
        return Mulligan(str(d["card"]))
    if kind == "end_mulligan":
        return EndMulligan()
    if kind == "play_card":
        position = d.get("position")
        return PlayCard(
            str(d["card"]),
            Row(d["row"]) if d.get("row") is not None else None,
            int(position) if position is not None else None,
        )
    if kind == "use_order":
        return UseOrder(str(d["instance"]))
    if kind == "pass":
        return Pass()
    if kind == "choose":
        return Choose(int(d["option"]))
    if kind == "cancel_choice":
        return CancelChoice()
    raise ValueError(f"unknown intent kind {kind!r}")
