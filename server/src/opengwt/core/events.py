"""Domain events: what happened, in order. The client animates them; the server broadcasts them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Events that carry a card's identity for its owner only (docs/protocol/match.md §8).
PRIVATE_IDENTITY = frozenset({"card_drawn", "card_redrawn"})
# The fields of an event only the player it concerns sees.
PRIVATE_FIELDS: dict[str, tuple[str, ...]] = {
    **{t: ("instance", "card") for t in sorted(PRIVATE_IDENTITY)},
    "choice_made": ("option",),
}


@dataclass(frozen=True)
class Event:
    seq: int
    type: str
    data: dict[str, Any]


def event_to_dict(event: Event) -> dict[str, Any]:
    return {"seq": event.seq, "type": event.type, **event.data}


def event_from_dict(d: dict[str, Any]) -> Event:
    data = {k: v for k, v in d.items() if k not in ("seq", "type")}
    return Event(int(d["seq"]), str(d["type"]), data)


def event_for_seat(event: Event, seat: int) -> Event:
    """The event as ``seat`` may see it: another player's draws and redraws lose their card, and
    another player's choice its option — only the chooser saw the options, and the index of one
    among cards from a hidden zone, which are sorted by card id, would tell something of them."""
    if event.data.get("seat") == seat:
        return event
    hidden = PRIVATE_FIELDS.get(event.type)
    if hidden is None:
        return event
    return Event(event.seq, event.type, {k: v for k, v in event.data.items() if k not in hidden})
